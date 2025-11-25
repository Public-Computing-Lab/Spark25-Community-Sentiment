"""
Google Drive to Vector DB Ingestion
Downloads new files from a shared Google Drive folder and adds them to the vector database.
For newsletters: extracts events page-by-page using LLM and stores in both SQL and vector DB.
"""
import json
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
    extract_pages_from_pdf,
    events_to_documents
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


def extract_events_from_page(page_text: str, page_num: int, source: str) -> List[Dict]:
    """
    Use LLM to extract structured events from a single newsletter page.
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
    
    prompt = f"""
You are reading PAGE {page_num} of a community newsletter.

Extract ALL events with their dates and times from this page.

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
- "event_name": Short descriptive name
- "event_date": Date label as written (e.g., "Monday", "June 3-5", "All week")
- "start_date": ISO date YYYY-MM-DD when event starts (or null if unclear)
- "end_date": ISO date YYYY-MM-DD when event ends (or null if same day)
- "start_time": 24-hour time HH:MM (or null)
- "end_time": 24-hour time HH:MM (or null)
- "raw_text": Original text describing the event (include full details)
- "location": Where the event takes place (or null)
- "category": Choose one best fit: "Youth/Family", "Public Meeting", "Arts/Culture", "Health/Wellness", "Housing", "Safety", "Education", "Other"

If there are NO events on this page, return an empty array: []

Be thorough but conservative: extract all clear events but never invent information.

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
        
        # Clean up potential code fences
        if text_response.startswith("```"):
            text_response = text_response.strip("`").strip()
            lines = text_response.splitlines()
            if lines and lines[0].strip().lower() in ("json", "javascript"):
                text_response = "\n".join(lines[1:]).strip()
        
        events = json.loads(text_response)
        
        if not isinstance(events, list):
            return []
        
        # Add source and page info to each event
        for event in events:
            event['source'] = source
            event['page_number'] = page_num
        
        return events
        
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
                            event.get('event_name', ''),
                            event.get('event_date', ''),
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


def add_events_to_calendar_vectordb(events: List[Dict]) -> int:
    """Add calendar events to the calendar vector database for semantic search."""
    if not events:
        return 0
    
    # Convert events to Documents
    documents = events_to_documents(events, source="google_drive_newsletter")
    
    if not documents:
        return 0
    
    embeddings = GeminiEmbeddings()
    
    try:
        if config.CALENDAR_VECTORDB_DIR.exists():
            vectordb = Chroma(
                persist_directory=str(config.CALENDAR_VECTORDB_DIR),
                embedding_function=embeddings
            )
            vectordb.add_documents(documents)
        else:
            vectordb = Chroma.from_documents(
                documents=documents,
                embedding=embeddings,
                persist_directory=str(config.CALENDAR_VECTORDB_DIR)
            )
        
        return len(documents)
    except Exception as e:
        print(f"  ⚠ Error adding events to calendar vector DB: {e}")
        return 0


def process_newsletter_pdf(file_path: Path, file_metadata: Dict) -> Dict:
    """
    Process a newsletter PDF page by page:
    1. Extract text from each page
    2. Use LLM to extract events from each page
    3. Store events in SQL and calendar vector DB
    4. Also create document chunks for the main vector DB
    
    Returns dict with 'documents' (for vector DB) and 'events' (extracted events)
    """
    source_name = file_metadata.get('name', 'unknown')
    print(f"  📰 Processing newsletter page-by-page: {source_name}")
    
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
    all_documents = []
    
    # Process each page
    for page_info in pages:
        page_num = page_info['page_num']
        total_pages = page_info['total_pages']
        page_text = page_info['text']
        
        if not page_text.strip():
            continue
        
        print(f"    📄 Page {page_num}/{total_pages}: ", end="")
        
        # Extract events from this page using LLM
        events = extract_events_from_page(page_text, page_num, source_name)
        
        if events:
            print(f"found {len(events)} events")
            all_events.extend(events)
        else:
            print("no events")
        
        # Also create document chunks for the vector DB
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_core.documents import Document
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2500,
            chunk_overlap=300,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        chunks = text_splitter.split_text(page_text)
        
        for i, chunk in enumerate(chunks):
            doc = Document(
                page_content=chunk,
                metadata={
                    'source': source_name,
                    'doc_type': 'client_upload',
                    'folder_category': 'newsletters',
                    'chunk_id': len(all_documents),
                    'page_num': page_num,
                    'total_pages': total_pages,
                    'drive_file_id': file_metadata.get('id', ''),
                    'modified_time': file_metadata.get('modifiedTime', ''),
                    'ingestion_date': datetime.now().isoformat(),
                    'file_extension': '.pdf'
                }
            )
            all_documents.append(doc)
    
    print(f"    ✓ Total: {len(all_events)} events, {len(all_documents)} document chunks")
    
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
    For newsletters: extracts events and stores in SQL + calendar vector DB.
    Returns summary statistics.
    """
    print("=" * 80)
    print("Starting Google Drive → Vector DB Sync")
    print("=" * 80)
    
    stats = {
        'files_processed': 0,
        'chunks_added': 0,
        'events_extracted': 0,
        'events_sql_inserted': 0,
        'events_vectordb_added': 0,
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
        
        # List new files
        print(f"Scanning folder {config.GOOGLE_DRIVE_FOLDER_ID}...")
        new_files = list_new_files_from_drive(
            service, 
            config.GOOGLE_DRIVE_FOLDER_ID, 
            processed_files
        )
        
        print(f"Found {len(new_files)} new or updated files to process.")
        
        if not new_files:
            print("No new files to process. Exiting.")
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
        
        # Insert events to SQL database
        if all_events:
            print(f"\nInserting {len(all_events)} events into SQL database...")
            inserted = insert_events_to_db(all_events)
            stats['events_sql_inserted'] = inserted
            print(f"✓ Inserted {inserted} events to SQL")
            
            # Add events to calendar vector DB
            print(f"Adding {len(all_events)} events to calendar vector database...")
            vectordb_added = add_events_to_calendar_vectordb(all_events)
            stats['events_vectordb_added'] = vectordb_added
            print(f"✓ Added {vectordb_added} events to calendar vector DB")
        
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
    print(f"Events extracted: {stats['events_extracted']}")
    print(f"Events inserted (SQL): {stats['events_sql_inserted']}")
    print(f"Events added (Calendar Vector DB): {stats['events_vectordb_added']}")
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

