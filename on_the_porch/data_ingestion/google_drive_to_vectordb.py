"""
Google Drive to Vector DB Ingestion
Downloads new files from a shared Google Drive folder and adds them to the vector database.
For newsletters: extracts events page-by-page using LLM and stores in SQL.
"""
import json
import re
import sys
from pathlib import Path
from typing import List, Dict
from datetime import datetime

# Google Drive API
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# LLM for event extraction
import google.generativeai as genai

# Document processing
from langchain_community.vectorstores import Chroma

# Local imports
sys.path.insert(0, str(Path(__file__).parent.parent / "rag stuff"))
from retrieval import GeminiEmbeddings

# SQL for events
sys.path.insert(0, str(Path(__file__).parent.parent))
import sql_chat.app4 as app4

import config
from utils.document_processor import (
    process_file_to_documents,
    extract_pages_from_pdf
)


def load_sync_state() -> dict:
    """Load the state of what files have been synced."""
    if config.SYNC_STATE_FILE.exists():
        try:
            return json.loads(config.SYNC_STATE_FILE.read_text())
        except Exception:
            return {"processed_files": {}, "last_sync": None}
    return {"processed_files": {}, "last_sync": None}


def save_sync_state(state: dict) -> None:
    """Save the sync state to track processed files."""
    state["last_sync"] = datetime.now().isoformat()
    config.SYNC_STATE_FILE.write_text(json.dumps(state, indent=2))


def get_drive_service():
    """Authenticate and return Google Drive service."""
    if not Path(config.GOOGLE_CREDENTIALS_PATH).exists():
        raise FileNotFoundError(
            f"Google credentials file not found: {config.GOOGLE_CREDENTIALS_PATH}"
        )
    
    creds = ServiceAccountCredentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_PATH,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)


def list_subfolders(service, folder_id: str) -> List[dict]:
    """
    List all subfolders in a Google Drive folder.
    Returns list of folder metadata: {id, name}
    """
    query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    
    try:
        results = service.files().list(
            q=query,
            fields="files(id, name)",
            pageSize=100
        ).execute()
    except Exception as e:
        raise RuntimeError(f"Failed to list subfolders from Google Drive: {e}")
    
    return results.get('files', [])


def list_files_in_folder(service, folder_id: str, folder_name: str, processed_files: dict) -> List[dict]:
    """
    List all files in a specific Google Drive folder that haven't been processed yet.
    Returns list of file metadata with folder_category included.
    """
    query = f"'{folder_id}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false"
    
    try:
        results = service.files().list(
            q=query,
            fields="files(id, name, mimeType, modifiedTime, md5Checksum)",
            pageSize=1000
        ).execute()
    except Exception as e:
        raise RuntimeError(f"Failed to list files from folder '{folder_name}': {e}")
    
    all_files = results.get('files', [])
    
    # Filter out already processed files and add folder category
    new_files = []
    for file in all_files:
        file_id = file['id']
        modified_time = file.get('modifiedTime', '')
        
        # Check if we've seen this file with the same modification time
        if file_id in processed_files:
            if processed_files[file_id].get('modifiedTime') == modified_time:
                continue  # Already processed this version
        
        # Check file extension
        ext = Path(file['name']).suffix.lower()
        if ext in config.SUPPORTED_EXTENSIONS:
            # Add folder category to file metadata
            file['folder_category'] = folder_name
            new_files.append(file)
    
    return new_files


def list_new_files_from_drive(service, folder_id: str, processed_files: dict) -> List[dict]:
    """
    List all files in the Google Drive folder and its subfolders that haven't been processed yet.
    Files are tagged with their folder_category (subfolder name).
    Returns list of file metadata: {id, name, mimeType, modifiedTime, folder_category}
    """
    if not folder_id:
        raise ValueError("GOOGLE_DRIVE_FOLDER_ID is not set")
    
    all_new_files = []
    
    # First, get files directly in the root folder (tagged as 'root')
    root_files = list_files_in_folder(service, folder_id, "root", processed_files)
    all_new_files.extend(root_files)
    if root_files:
        print(f"  Found {len(root_files)} new files in root folder")
    
    # Then, scan each subfolder
    subfolders = list_subfolders(service, folder_id)
    print(f"  Found {len(subfolders)} subfolders: {[f['name'] for f in subfolders]}")
    
    for subfolder in subfolders:
        subfolder_files = list_files_in_folder(
            service, 
            subfolder['id'], 
            subfolder['name'],  # Use subfolder name as category
            processed_files
        )
        all_new_files.extend(subfolder_files)
        if subfolder_files:
            print(f"  Found {len(subfolder_files)} new files in '{subfolder['name']}'")
    
    return all_new_files


def download_file(service, file_id: str, file_name: str) -> Path:
    """Download a file from Google Drive to temp directory."""
    request = service.files().get_media(fileId=file_id)
    local_path = config.TEMP_DOWNLOAD_DIR / file_name
    
    try:
        with io.FileIO(local_path, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status and config.VERBOSE_LOGGING:
                    print(f"    Download {int(status.progress() * 100)}%")
    except Exception as e:
        raise RuntimeError(f"Failed to download file {file_name}: {e}")
    
    return local_path


def _extract_date_from_pdf_content(file_path: Path) -> str | None:
    """
    Extract publication date from the first page of the PDF.
    Looks for patterns like "Thursday, November 20, 2025" or "Volume X Issue Y, [Day], [Month] [Day], [Year]"
    Returns date in YYYY-MM-DD format or None if not found.
    """
    try:
        pages = extract_pages_from_pdf(file_path)
        if not pages or len(pages) == 0:
            return None
        
        # Get first page text
        first_page_text = pages[0]['text']
        
        # Look for date patterns in the first page
        # Pattern 1: "Thursday, November 20, 2025" or "Monday, January 1, 2025"
        date_patterns = [
            # Full format: "Day, Month Day, Year"
            r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+'
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+'
            r'(\d{1,2}),\s+(\d{4})',
            # Without day of week: "November 20, 2025"
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+'
            r'(\d{1,2}),\s+(\d{4})',
            # Alternative: "Nov 20, 2025"
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+'
            r'(\d{1,2}),\s+(\d{4})',
        ]
        
        month_map = {
            'january': '01', 'february': '02', 'march': '03', 'april': '04',
            'may': '05', 'june': '06', 'july': '07', 'august': '08',
            'september': '09', 'october': '10', 'november': '11', 'december': '12',
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
        }
        
        for pattern in date_patterns:
            match = re.search(pattern, first_page_text, re.IGNORECASE)
            if match:
                try:
                    if len(match.groups()) == 3:
                        month_name, day, year = match.groups()
                        month = month_map.get(month_name.lower(), None)
                        if month:
                            date_str = f"{year}-{month}-{day.zfill(2)}"
                            # Validate the date
                            datetime.strptime(date_str, '%Y-%m-%d')
                            return date_str
                except (ValueError, AttributeError):
                    continue
        
        return None
    except Exception as e:
        if config.VERBOSE_LOGGING:
            print(f"    ⚠ Could not extract date from PDF content: {e}")
        return None


def _extract_date_from_filename(filename: str) -> str | None:
    """
    Try to extract a publication date from newsletter filename.
    Common patterns: "REP 47_25web.pdf", "Newsletter_2025-01-15.pdf", "Jan15_2025.pdf"
    Returns date in YYYY-MM-DD format or None if not found.
    """
    import re
    
    # Try various date patterns
    patterns = [
        r'(\d{4})-(\d{2})-(\d{2})',  # YYYY-MM-DD
        r'(\d{2})/(\d{2})/(\d{4})',  # MM/DD/YYYY
        r'(\d{4})(\d{2})(\d{2})',     # YYYYMMDD
        r'(\d{2})_(\d{2})_(\d{4})',  # MM_DD_YYYY
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            try:
                if len(match.groups()) == 3:
                    if pattern == r'(\d{4})-(\d{2})-(\d{2})':
                        year, month, day = match.groups()
                    elif pattern == r'(\d{2})/(\d{2})/(\d{4})':
                        month, day, year = match.groups()
                    elif pattern == r'(\d{4})(\d{2})(\d{2})':
                        year, month, day = match.groups()
                    elif pattern == r'(\d{2})_(\d{2})_(\d{4})':
                        month, day, year = match.groups()
                    
                    date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    # Validate the date
                    datetime.strptime(date_str, '%Y-%m-%d')
                    return date_str
            except (ValueError, IndexError):
                continue
    
    # Try to extract year from patterns like "REP 47_25web.pdf" (year 2025)
    # But don't use this as a fallback - it's too unreliable
    # Instead, return None and let the file modification date be used
    # year_match = re.search(r'[_\s](\d{2})(?:web|\.pdf|$)', filename)
    # if year_match:
    #     year_suffix = year_match.group(1)
    #     # Assume 20XX for years 00-99
    #     current_year = datetime.now().year
    #     century = (current_year // 100) * 100
    #     year = century + int(year_suffix)
    #     # Use first day of year as fallback (better than nothing)
    #     return f"{year}-01-01"
    
    return None


def extract_events_from_page(page_text: str, page_num: int, source: str, publication_date: str = None) -> List[Dict]:
    """
    Use LLM to extract structured events from a single newsletter page.
    
    Args:
        page_text: Text content from the page
        page_num: Page number
        source: Source identifier (filename)
        publication_date: Newsletter publication date in YYYY-MM-DD format (used to infer exact dates from day names)
    """
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured")
    
    if not page_text.strip() or len(page_text.strip()) < 50:
        return []
    
    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(config.GEMINI_MODEL)
    
    # Truncate if too long
    max_chars = 8000
    if len(page_text) > max_chars:
        page_text = page_text[:max_chars] + "\n\n[... text truncated ...]"
    
    # Build date context for the prompt
    date_context = ""
    if publication_date:
        try:
            pub_dt = datetime.strptime(publication_date, '%Y-%m-%d')
            date_context = f"""
IMPORTANT DATE CONTEXT:
- Newsletter publication date: {publication_date} ({pub_dt.strftime('%A, %B %d, %Y')})
- Use this date to convert day-of-week references (Monday, Tuesday, etc.) to exact dates
- For example, if the newsletter is dated {publication_date} and an event says "Monday", calculate which Monday that refers to
- Events typically occur in the week following the newsletter publication date
- Always prefer exact dates (YYYY-MM-DD) over day names when possible
"""
        except Exception:
            pass
    
    prompt = f"""
You are reading PAGE {page_num} of a community newsletter.
{date_context}
Extract ALL events with their dates and times from this page.

CRITICAL: Convert day-of-week references (Monday, Tuesday, Wednesday, etc.) to EXACT dates (YYYY-MM-DD) using the newsletter publication date as reference.
- If an event says "Monday" and the newsletter is dated {publication_date or 'unknown'}, calculate the exact Monday date
- Events in newsletters typically refer to the upcoming week
- Always provide start_date and end_date in ISO format (YYYY-MM-DD) when possible
- Only use null if the date truly cannot be determined

Return ONLY valid JSON (no explanations, no markdown, no code fences), in this exact format:
[
  {{
    "event_name": "...",
    "event_date": "...",
    "start_date": "YYYY-MM-DD or null",
    "end_date": "YYYY-MM-DD or null",
    "start_time": "HH:MM or null",
    "end_time": "HH:MM or null",
    "raw_text": "...",
    "location": "... or null",
    "category": "... or null"
  }},
  ...
]

Field rules:
- "event_name": Short descriptive name (REQUIRED - must always be provided)
- "event_date": Date label as written (REQUIRED - e.g., "Monday", "June 3-5", "All week", "Ongoing", "TBA" - always provide something, even if approximate)
- "start_date": ISO date YYYY-MM-DD when event starts - CONVERT day names to exact dates using publication date
- "end_date": ISO date YYYY-MM-DD when event ends (or null if same day) - CONVERT day names to exact dates
- "start_time": 24-hour time HH:MM (or null)
- "end_time": 24-hour time HH:MM (or null)
- "raw_text": Original text describing the event (include full details)
- "location": Where the event takes place (or null)
- "category": Choose one best fit: "Youth/Family", "Public Meeting", "Arts/Culture", "Health/Wellness", "Housing", "Safety", "Education", "Other"

If there are NO events on this page, return an empty array: []

Be thorough but conservative: extract all clear events but never invent information, but DO convert day names to exact dates when the publication date is provided.

Page {page_num} text:
\"\"\"
{page_text}
\"\"\"
"""
    
    try:
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0}
        )
        text_response = (response.text or "").strip()
        
        # Check if response is empty
        if not text_response:
            print(f"    ⚠ Empty response from LLM for page {page_num}")
            return []
        
        # Clean up potential code fences
        if text_response.startswith("```"):
            text_response = text_response.strip("`").strip()
            lines = text_response.splitlines()
            if lines and lines[0].strip().lower() in ("json", "javascript"):
                text_response = "\n".join(lines[1:]).strip()
        
        # Try to extract JSON if it's embedded in text
        # Look for JSON array pattern
        json_match = re.search(r'\[[\s\S]*\]', text_response)
        if json_match:
            text_response = json_match.group(0)
        
        # Validate we have something that looks like JSON
        text_response = text_response.strip()
        if not text_response or not (text_response.startswith('[') or text_response.startswith('{')):
            print(f"    ⚠ Invalid JSON response format for page {page_num} (response: {text_response[:100]}...)")
            return []
        
        try:
            events = json.loads(text_response)
        except json.JSONDecodeError as json_err:
            # Try to fix common JSON issues
            # Remove trailing commas before closing brackets/braces
            text_response = re.sub(r',\s*([}\]])', r'\1', text_response)
            
            # Remove control characters (except newlines/tabs in string values which should be escaped)
            # Replace unescaped control characters with spaces
            # But we need to be careful - let's try a different approach
            # Remove control characters that aren't part of valid JSON structure
            # This regex removes control chars except \n, \r, \t when they're escaped
            text_response = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text_response)
            
            # Try parsing again
            try:
                events = json.loads(text_response)
            except json.JSONDecodeError:
                # Last resort: try to extract just the JSON array/object more aggressively
                # Find the first [ or { and last ] or }
                start_idx = text_response.find('[')
                if start_idx == -1:
                    start_idx = text_response.find('{')
                if start_idx != -1:
                    end_idx = text_response.rfind(']')
                    if end_idx == -1 or end_idx < start_idx:
                        end_idx = text_response.rfind('}')
                    if end_idx != -1 and end_idx > start_idx:
                        text_response = text_response[start_idx:end_idx+1]
                        # Clean again
                        text_response = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text_response)
                        try:
                            events = json.loads(text_response)
                        except json.JSONDecodeError:
                            print(f"    ⚠ JSON parse error for page {page_num}: {json_err}")
                            print(f"    Response preview: {text_response[:200]}...")
                            return []
                else:
                    print(f"    ⚠ JSON parse error for page {page_num}: {json_err}")
                    print(f"    Response preview: {text_response[:200]}...")
                    return []
        
        if not isinstance(events, list):
            print(f"    ⚠ Expected list but got {type(events).__name__} for page {page_num}")
            return []
        
        # Validate and clean events before returning
        validated_events = []
        for event in events:
            if not isinstance(event, dict):
                continue
            
            # Ensure required fields exist
            if not event.get('event_name'):
                continue  # Skip events without names
            
            # Ensure event_date exists (required by database)
            if not event.get('event_date'):
                # Try to construct from start_date/end_date or use placeholder
                event['event_date'] = event.get('start_date') or event.get('end_date') or 'no info'
            
            # Clean string fields (remove extra whitespace)
            for key in ['event_name', 'event_date', 'raw_text', 'location', 'category']:
                if key in event and isinstance(event[key], str):
                    event[key] = event[key].strip()
            
            # Validate date formats (start_date and end_date should be YYYY-MM-DD or null)
            for date_key in ['start_date', 'end_date']:
                if date_key in event and event[date_key]:
                    date_val = str(event[date_key]).strip()
                    if date_val.lower() not in ('null', 'none', ''):
                        # Try to validate date format
                        try:
                            datetime.strptime(date_val, '%Y-%m-%d')
                        except ValueError:
                            # Invalid date format - set to null
                            event[date_key] = None
            
            # Validate time formats (should be HH:MM or null)
            for time_key in ['start_time', 'end_time']:
                if time_key in event and event[time_key]:
                    time_val = str(event[time_key]).strip()
                    if time_val.lower() not in ('null', 'none', ''):
                        # Try to validate time format (HH:MM or HH:MM:SS)
                        if not re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', time_val):
                            event[time_key] = None
            
            # Add source and page info
            event['source'] = source
            event['page_number'] = page_num
            
            validated_events.append(event)
        
        return validated_events
        
    except Exception as e:
        print(f"    ⚠ Error extracting events from page {page_num}: {e}")
        return []


def insert_events_to_db(events: List[Dict]) -> int:
    """Insert events into the weekly_events SQL table."""
    if not events:
        return 0
    
    if not config.DATABASE_URL:
        print("  ⚠ DATABASE_URL not configured, skipping SQL insert")
        return 0
    
    conn = app4._get_db_connection()
    inserted_count = 0
    
    try:
        with conn.cursor() as cur:
            # Ensure weekly_events table exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS weekly_events (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    source_pdf VARCHAR(255) NULL,
                    page_number INT NULL,
                    event_name VARCHAR(255) NOT NULL,
                    event_date VARCHAR(255) NOT NULL,
                    start_date DATE NULL,
                    end_date DATE NULL,
                    start_time TIME NULL,
                    end_time TIME NULL,
                    raw_text TEXT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            
            # Check if category column exists, add it if not
            cur.execute("SHOW COLUMNS FROM weekly_events LIKE 'category'")
            if not cur.fetchone():
                try:
                    print("  ℹ Adding 'category' column to weekly_events table...")
                    cur.execute("ALTER TABLE weekly_events ADD COLUMN category TEXT")
                except Exception as e:
                    print(f"  ⚠ Could not add category column: {e}")

            for event in events:
                try:
                    # Validate required fields
                    event_name = event.get('event_name', '').strip()
                    event_date = event.get('event_date', '').strip()
                    
                    # Skip events without required fields
                    if not event_name:
                        if config.VERBOSE_LOGGING:
                            print(f"    ⚠ Skipping event with no name")
                        continue
                    
                    # event_date is required by database - provide default if missing
                    if not event_date:
                        # Try to use start_date or end_date as fallback
                        event_date = event.get('start_date') or event.get('end_date') or ''
                        if not event_date:
                            # Last resort: use a placeholder
                            event_date = 'no info'
                    
                    cur.execute(
                        """
                        INSERT INTO weekly_events (
                            source_pdf,
                            page_number,
                            event_name,
                            event_date,
                            start_date,
                            end_date,
                            start_time,
                            end_time,
                            raw_text,
                            category
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            event.get('source', 'google_drive_newsletter'),
                            event.get('page_number'),
                            event_name,
                            event_date,
                            event.get('start_date'),
                            event.get('end_date'),
                            event.get('start_time'),
                            event.get('end_time'),
                            event.get('raw_text', ''),
                            event.get('category', 'Other')
                        )
                    )
                    inserted_count += 1
                except Exception as e:
                    if config.VERBOSE_LOGGING:
                        print(f"    ⚠ Could not insert event '{event.get('event_name')}': {e}")
        
        conn.commit()
    finally:
        conn.close()
    
    return inserted_count


def process_newsletter_pdf(file_path: Path, file_metadata: Dict) -> Dict:
    """
    Process a newsletter PDF page by page:
    1. Extract text from each page
    2. Use LLM to extract events from each page
    3. Store events in SQL
    4. Also create document chunks for the main vector DB
    
    Returns dict with 'documents' (for vector DB) and 'events' (extracted events)
    """
    source_name = file_metadata.get('name', 'unknown')
    print(f"  📰 Processing newsletter page-by-page: {source_name}")
    
    # Try to determine publication date from PDF content first (most accurate)
    publication_date = _extract_date_from_pdf_content(file_path)
    
    # Fallback to filename
    if not publication_date:
        publication_date = _extract_date_from_filename(source_name)
    
    # Final fallback to file modification date
    if not publication_date:
        try:
            modified_time = file_metadata.get('modifiedTime', '')
            if modified_time:
                # Parse ISO format datetime and extract date
                pub_dt = datetime.fromisoformat(modified_time.replace('Z', '+00:00'))
                publication_date = pub_dt.strftime('%Y-%m-%d')
        except Exception:
            pass
    
    if publication_date:
        print(f"    📅 Using publication date: {publication_date}")
    else:
        print(f"    ⚠ Could not determine publication date - day names may not be converted to exact dates")
    
    # Extract pages
    try:
        pages = extract_pages_from_pdf(file_path)
    except Exception as e:
        print(f"    ⚠ Failed to extract pages: {e}")
        return {'documents': [], 'events': []}
    
    if not pages:
        print(f"    ⚠ No pages extracted from PDF")
        return {'documents': [], 'events': []}
    
    print(f"    Found {len(pages)} pages")
    
    all_events = []
    # We no longer add newsletter pages to the vector DB; only extract events for SQL
    all_documents: List = []
    
    # Process each page
    for page_info in pages:
        page_num = page_info['page_num']
        total_pages = page_info['total_pages']
        page_text = page_info['text']
        
        if not page_text.strip():
            continue
        
        print(f"    📄 Page {page_num}/{total_pages}: ", end="")
        
        # Extract events from this page using LLM (pass publication date for date inference)
        events = extract_events_from_page(page_text, page_num, source_name, publication_date=publication_date)
        
        if events:
            print(f"found {len(events)} events")
            all_events.extend(events)
        else:
            print("no events")
        
        # No vectordb chunks created for newsletters anymore
    
    print(f"    ✓ Total: {len(all_events)} events, 0 document chunks (vectordb disabled for newsletters)")
    
    return {
        'documents': all_documents,
        'events': all_events
    }


def add_documents_to_vectordb(documents: List) -> None:
    """Add new documents to the existing vector database."""
    if not documents:
        print("No documents to add.")
        return
    
    embeddings = GeminiEmbeddings()
    
    # Load existing vector DB or create new one
    if config.VECTORDB_DIR.exists():
        vectordb = Chroma(
            persist_directory=str(config.VECTORDB_DIR),
            embedding_function=embeddings
        )
        # Add new documents
        vectordb.add_documents(documents)
        print(f"✓ Added {len(documents)} new document chunks to existing vector DB.")
    else:
        # Create new vector DB
        vectordb = Chroma.from_documents(
            documents=documents,
            embedding=embeddings,
            persist_directory=str(config.VECTORDB_DIR)
        )
        print(f"✓ Created new vector DB with {len(documents)} document chunks.")


def delete_chunks_by_file_id(file_id: str) -> int:
    """Delete all chunks from vector database that belong to a specific Google Drive file ID."""
    if not config.VECTORDB_DIR.exists():
        return 0
    
    try:
        embeddings = GeminiEmbeddings()
        vectordb = Chroma(
            persist_directory=str(config.VECTORDB_DIR),
            embedding_function=embeddings
        )
        
        # Get all document IDs that match this file_id
        results = vectordb.get(where={"drive_file_id": file_id})
        
        if results and results.get('ids') and len(results['ids']) > 0:
            # Delete by IDs
            vectordb.delete(ids=results['ids'])
            return len(results['ids'])
        else:
            # No chunks found for this file_id
            return 0
        
    except Exception as e:
        if config.VERBOSE_LOGGING:
            print(f"    ⚠ Error deleting chunks for file ID {file_id}: {e}")
        return 0


def get_all_current_file_ids(service, folder_id: str) -> set:
    """Get all file IDs currently in Google Drive folder (including subfolders)."""
    current_file_ids = set()
    
    try:
        # Get files in root folder
        query = f"'{folder_id}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false"
        results = service.files().list(
            q=query,
            fields="files(id)",
            pageSize=1000
        ).execute()
        
        for file in results.get('files', []):
            current_file_ids.add(file['id'])
        
        # Get subfolders and their files
        subfolders = list_subfolders(service, folder_id)
        for subfolder in subfolders:
            subfolder_query = f"'{subfolder['id']}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false"
            subfolder_results = service.files().list(
                q=subfolder_query,
                fields="files(id)",
                pageSize=1000
            ).execute()
            
            for file in subfolder_results.get('files', []):
                current_file_ids.add(file['id'])
    
    except Exception as e:
        if config.VERBOSE_LOGGING:
            print(f"    ⚠ Error getting current file IDs: {e}")
    
    return current_file_ids


def remove_deleted_files_from_vectordb(service, folder_id: str, processed_files: dict) -> dict:
    """
    Detect files deleted from Google Drive and remove their chunks from vector DB.
    Returns dict with deletion stats.
    """
    deletion_stats = {
        'files_deleted': 0,
        'chunks_removed': 0,
        'errors': []
    }
    
    if not processed_files:
        return deletion_stats
    
    print("\nChecking for deleted files in Google Drive...")
    
    try:
        # Get all file IDs currently in Drive
        current_file_ids = get_all_current_file_ids(service, folder_id)
        
        # Find files that were processed but no longer exist in Drive
        processed_file_ids = set(processed_files.keys())
        deleted_file_ids = processed_file_ids - current_file_ids
        
        if not deleted_file_ids:
            print("  ✓ No deleted files detected")
            return deletion_stats
        
        print(f"  Found {len(deleted_file_ids)} deleted file(s) to remove from vector DB")
        
        # Delete chunks for each deleted file
        for file_id in deleted_file_ids:
            file_name = processed_files[file_id].get('name', 'unknown')
            expected_chunks = processed_files[file_id].get('chunks', 0)
            
            try:
                print(f"  🗑️  Removing chunks for deleted file: {file_name}")
                chunks_deleted = delete_chunks_by_file_id(file_id)
                
                if chunks_deleted > 0:
                    print(f"    ✓ Deleted {chunks_deleted} chunk(s)")
                else:
                    print(f"    ⚠ No chunks found to delete (may have been already removed)")
                
                # Remove from processed_files dict
                del processed_files[file_id]
                
                deletion_stats['files_deleted'] += 1
                deletion_stats['chunks_removed'] += chunks_deleted
                
            except Exception as e:
                error_msg = f"Error removing chunks for {file_name}: {str(e)}"
                print(f"    ✗ {error_msg}")
                deletion_stats['errors'].append(error_msg)
        
        if deletion_stats['files_deleted'] > 0:
            print(f"  ✓ Removed {deletion_stats['files_deleted']} deleted file(s) from vector DB")
    
    except Exception as e:
        error_msg = f"Error detecting deleted files: {str(e)}"
        print(f"  ✗ {error_msg}")
        deletion_stats['errors'].append(error_msg)
    
    return deletion_stats


def cleanup_temp_files() -> None:
    """Clean up temporary downloaded files."""
    for file in config.TEMP_DOWNLOAD_DIR.glob("*"):
        if file.is_file():
            try:
                file.unlink()
            except Exception:
                pass


def sync_google_drive_to_vectordb() -> dict:
    """
    Main function to sync Google Drive files to vector database.
    For newsletters: extracts events and stores in SQL.
    Returns summary statistics.
    """
    print("=" * 80)
    print("Starting Google Drive → Vector DB Sync")
    print("=" * 80)
    
    stats = {
        'files_processed': 0,
        'chunks_added': 0,
        'files_deleted': 0,
        'chunks_removed': 0,
        'events_extracted': 0,
        'events_sql_inserted': 0,
        'errors': []
    }
    
    try:
        # Validate configuration
        errors = config.validate_config()
        drive_errors = [e for e in errors if 'GOOGLE_DRIVE' in e or 'Google credentials' in e]
        if drive_errors:
            for error in drive_errors:
                print(f"✗ Configuration error: {error}")
                stats['errors'].append(error)
            return stats
        
        # Load sync state
        state = load_sync_state()
        processed_files = state.get('processed_files', {})
        
        # Get Drive service
        print("Authenticating with Google Drive...")
        service = get_drive_service()
        print("✓ Authenticated successfully")
        
        # Check for and remove deleted files from vector DB
        deletion_stats = remove_deleted_files_from_vectordb(
            service, 
            config.GOOGLE_DRIVE_FOLDER_ID, 
            processed_files
        )
        stats['files_deleted'] = deletion_stats['files_deleted']
        stats['chunks_removed'] = deletion_stats['chunks_removed']
        stats['errors'].extend(deletion_stats['errors'])
        
        # List new files
        print(f"\nScanning folder {config.GOOGLE_DRIVE_FOLDER_ID}...")
        new_files = list_new_files_from_drive(
            service, 
            config.GOOGLE_DRIVE_FOLDER_ID, 
            processed_files
        )
        
        print(f"Found {len(new_files)} new or updated files to process.")
        
        if not new_files:
            print("No new files to process.")
            # Still save sync state in case files were deleted
            state['processed_files'] = processed_files
            save_sync_state(state)
            if stats['files_deleted'] > 0:
                print("✓ Sync state updated (deleted files removed)")
            return stats
        
        all_documents = []
        all_events = []
        
        # Process each new file
        for i, file_meta in enumerate(new_files[:config.MAX_FILES_PER_RUN], 1):
            try:
                folder_cat = file_meta.get('folder_category', 'root')
                file_ext = Path(file_meta['name']).suffix.lower()
                print(f"\n[{i}/{len(new_files)}] Processing: {file_meta['name']} (from '{folder_cat}')")
                
                # Download file
                local_path = download_file(service, file_meta['id'], file_meta['name'])
                print(f"  ✓ Downloaded to {local_path.name}")
                
                # Special processing for newsletters (PDFs)
                if folder_cat == 'newsletters' and file_ext == '.pdf':
                    # Process newsletter page-by-page with event extraction
                    result = process_newsletter_pdf(local_path, file_meta)
                    documents = result['documents']
                    events = result['events']
                    
                    all_documents.extend(documents)
                    all_events.extend(events)
                    
                    stats['events_extracted'] += len(events)
                    
                    # Mark as processed
                    processed_files[file_meta['id']] = {
                        'name': file_meta['name'],
                        'folder_category': folder_cat,
                        'modifiedTime': file_meta.get('modifiedTime', ''),
                        'processed_at': datetime.now().isoformat(),
                        'chunks': len(documents),
                        'events': len(events)
                    }
                else:
                    # Standard processing for non-newsletter files
                    documents = process_file_to_documents(local_path, file_meta)
                    all_documents.extend(documents)
                    
                    # Mark as processed
                    processed_files[file_meta['id']] = {
                        'name': file_meta['name'],
                        'folder_category': folder_cat,
                        'modifiedTime': file_meta.get('modifiedTime', ''),
                        'processed_at': datetime.now().isoformat(),
                        'chunks': len(documents)
                    }
                    
                    print(f"  ✓ Extracted {len(documents)} chunks")
                
                stats['files_processed'] += 1
                
            except Exception as e:
                error_msg = f"Error processing {file_meta['name']}: {str(e)}"
                print(f"  ✗ {error_msg}")
                stats['errors'].append(error_msg)
        
        # Add all documents to main vector DB
        if all_documents:
            print(f"\nAdding {len(all_documents)} chunks to vector database...")
            add_documents_to_vectordb(all_documents)
            stats['chunks_added'] = len(all_documents)
        
        # Insert events to SQL database (events are SQL-only, no vector DB)
        if all_events:
            print(f"\nInserting {len(all_events)} events into SQL database...")
            inserted = insert_events_to_db(all_events)
            stats['events_sql_inserted'] = inserted
            print(f"✓ Inserted {inserted} events to SQL")
        
        # Save updated sync state
        state['processed_files'] = processed_files
        save_sync_state(state)
        print("✓ Sync state saved")
        
        # Cleanup
        cleanup_temp_files()
        print("✓ Temporary files cleaned up")
        
    except Exception as e:
        error_msg = f"Fatal error during sync: {str(e)}"
        print(f"\n✗ {error_msg}")
        stats['errors'].append(error_msg)
    
    print("\n" + "=" * 80)
    print("Google Drive Sync Complete")
    print(f"Files processed: {stats['files_processed']}")
    print(f"Document chunks added: {stats['chunks_added']}")
    if stats['files_deleted'] > 0:
        print(f"Files deleted: {stats['files_deleted']}")
        print(f"Chunks removed: {stats['chunks_removed']}")
    print(f"Events extracted: {stats['events_extracted']}")
    print(f"Events inserted (SQL): {stats['events_sql_inserted']}")
    print(f"Errors: {len(stats['errors'])}")
    print("=" * 80)
    
    return stats


if __name__ == "__main__":
    try:
        sync_google_drive_to_vectordb()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        sys.exit(1)

