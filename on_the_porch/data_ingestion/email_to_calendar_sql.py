"""
Email Newsletter to Calendar SQL Ingestion
Reads newsletters from a dedicated email inbox and extracts events to SQL database.
Uses Gmail API with OAuth 2.0 authentication (more reliable than IMAP).
"""
import json
import sys
import base64
from pathlib import Path
from typing import List, Dict
from datetime import datetime, timedelta
import email

# Gmail API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# LLM for extraction
import google.generativeai as genai

# Local imports
sys.path.insert(0, str(Path(__file__).parent.parent))
import sql_chat.app4 as app4

import config
from utils.email_parser import (
    extract_text_from_email,
    extract_pdf_attachments,
    get_email_subject,
    get_email_date
)

# Gmail OAuth scopes - using Gmail API (readonly)
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def load_email_sync_state() -> dict:
    """Load state of which emails have been processed."""
    if config.EMAIL_SYNC_STATE_FILE.exists():
        try:
            return json.loads(config.EMAIL_SYNC_STATE_FILE.read_text())
        except Exception:
            return {"processed_email_ids": [], "last_sync": None}
    return {"processed_email_ids": [], "last_sync": None}


def save_email_sync_state(state: dict) -> None:
    """Save email sync state."""
    state["last_sync"] = datetime.now().isoformat()
    config.EMAIL_SYNC_STATE_FILE.write_text(json.dumps(state, indent=2))


def get_gmail_credentials() -> Credentials:
    """Get or refresh Gmail OAuth 2.0 credentials."""
    creds = None
    token_path = Path(config.GMAIL_TOKEN_PATH)
    
    # Load existing token if available
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            pass
    
    # If no valid credentials, go through OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh the token
            try:
                creds.refresh(Request())
            except Exception:
                # If refresh fails, re-authenticate
                creds = None
        
        if not creds:
            # Run OAuth flow (opens browser for user to authorize)
            credentials_path = Path(config.GMAIL_CREDENTIALS_PATH)
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"Gmail OAuth credentials not found: {config.GMAIL_CREDENTIALS_PATH}\n"
                    "Please download credentials from Google Cloud Console."
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            # Use fixed port 8080 so redirect URI is predictable
            creds = flow.run_local_server(port=8080)
        
        # Save the credentials for next run
        token_path.write_text(creds.to_json())
    
    return creds


def get_gmail_service():
    """Get authenticated Gmail API service."""
    if not config.EMAIL_ADDRESS:
        raise ValueError("NEWSLETTER_EMAIL_ADDRESS not configured")
    
    try:
        # Get OAuth credentials
        creds = get_gmail_credentials()
        
        # Build Gmail API service
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Gmail API: {e}")


def get_recent_newsletters(service, processed_ids: List[str], days_back: int = 7) -> List[tuple]:
    """
    Fetch recent newsletters using Gmail API.
    Returns list of (email_id, email_message) tuples.
    """
    try:
        # Calculate date for query
        since_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y/%m/%d')
        
        # Search for recent emails
        query = f'after:{since_date}'
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=100
        ).execute()
        
        messages = results.get('messages', [])
        
        newsletters = []
        for msg_ref in messages:
            msg_id = msg_ref['id']
            
            # Skip if already processed
            if msg_id in processed_ids:
                continue
            
            # Get full message
            try:
                message = service.users().messages().get(
                    userId='me',
                    id=msg_id,
                    format='raw'
                ).execute()
                
                # Decode the raw message
                raw_email = base64.urlsafe_b64decode(message['raw'])
                msg = email.message_from_bytes(raw_email)
                
                newsletters.append((msg_id, msg))
            except Exception:
                continue
        
        return newsletters
        
    except Exception as e:
        raise RuntimeError(f"Failed to fetch emails from Gmail API: {e}")


def extract_events_with_llm(text: str, source: str, publication_date: str = None) -> List[Dict]:
    """
    Use LLM to extract structured events from newsletter text.
    
    Args:
        text: Newsletter text content
        source: Source identifier
        publication_date: Newsletter publication date in YYYY-MM-DD format (used to infer exact dates from day names)
    """
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured")
    
    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(config.GEMINI_MODEL)
    
    # Truncate very long text to avoid token limits
    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... text truncated ...]"
    
    # Build date context for the prompt
    date_context = ""
    if publication_date:
        try:
            from datetime import datetime
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
You are reading a community newsletter or calendar listing events.
{date_context}
Extract ALL events with their dates and times from the text below.

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
    "location": "... or null"
  }},
  ...
]

Field rules:
- "event_name": Short descriptive name
- "event_date": Date label as written (e.g., "Monday", "June 3-5", "All week") - keep original text
- "start_date": ISO date YYYY-MM-DD when event starts - CONVERT day names to exact dates using publication date
- "end_date": ISO date YYYY-MM-DD when event ends (or null if same day) - CONVERT day names to exact dates
- "start_time": 24-hour time HH:MM (or null)
- "end_time": 24-hour time HH:MM (or null)
- "raw_text": Original text describing the event
- "location": Where the event takes place (or null)

Be conservative: only extract clear events with dates. Never invent information, but DO convert day names to exact dates when the publication date is provided.

Text:
\"\"\"
{text}
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
        
        # Add source to each event
        for event in events:
            event['source'] = source
        
        return events
        
    except Exception as e:
        print(f"  ✗ Error extracting events with LLM: {e}")
        return []


def insert_events_to_db(events: List[Dict]) -> int:
    """Insert events into the weekly_events table."""
    if not events:
        return 0
    
    if not config.DATABASE_URL:
        raise ValueError("DATABASE_URL is not configured")
    
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
                            raw_text
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            event.get('source', 'email_newsletter'),
                            None,  # page_number not applicable for emails
                            event.get('event_name', ''),
                            event.get('event_date', ''),
                            event.get('start_date'),
                            event.get('end_date'),
                            event.get('start_time'),
                            event.get('end_time'),
                            event.get('raw_text', '')
                        )
                    )
                    inserted_count += 1
                except Exception as e:
                    if config.VERBOSE_LOGGING:
                        print(f"  ⚠ Could not insert event '{event.get('event_name')}': {e}")
        
        conn.commit()
    finally:
        conn.close()
    
    return inserted_count


def sync_email_newsletters_to_sql() -> dict:
    """
    Main function to sync email newsletters to calendar SQL database.
    Returns summary statistics.
    """
    print("=" * 80)
    print("Starting Email Newsletter → Calendar SQL Sync")
    print("=" * 80)
    
    stats = {
        'emails_processed': 0,
        'events_extracted': 0,
        'events_inserted': 0,
        'errors': []
    }
    
    try:
        # Validate configuration
        errors = config.validate_config()
        email_errors = [e for e in errors if 'EMAIL' in e.upper() or 'DATABASE' in e]
        if email_errors:
            for error in email_errors:
                print(f"✗ Configuration error: {error}")
                stats['errors'].append(error)
            return stats
        
        # Load sync state
        state = load_email_sync_state()
        processed_ids = state.get('processed_email_ids', [])
        
        # Connect to Gmail API
        print("Connecting to Gmail API...")
        service = get_gmail_service()
        print("✓ Connected successfully")
        
        # Get recent newsletters
        print(f"Scanning inbox for newsletters from last {config.EMAIL_LOOKBACK_DAYS} days...")
        newsletters = get_recent_newsletters(service, processed_ids, days_back=config.EMAIL_LOOKBACK_DAYS)
        
        print(f"Found {len(newsletters)} new newsletters to process.")
        
        if not newsletters:
            print("No new newsletters. Exiting.")
            return stats
        
        all_events = []
        
        # Process each newsletter
        for i, (email_id, msg) in enumerate(newsletters, 1):
            try:
                # Get subject and date
                subject = get_email_subject(msg)
                email_date = get_email_date(msg)
                
                # Try to parse publication date
                from email.utils import parsedate_to_datetime
                try:
                    pub_date = parsedate_to_datetime(email_date).strftime('%Y-%m-%d')
                except Exception:
                    pub_date = datetime.now().strftime('%Y-%m-%d')
                
                print(f"\n[{i}/{len(newsletters)}] Processing: {subject[:60]}...")
                
                # Extract text from email body
                email_text = extract_text_from_email(msg)
                
                # Extract text from PDF attachments
                pdf_texts = extract_pdf_attachments(msg)
                
                # Combine all text
                full_text = email_text
                if pdf_texts:
                    full_text += "\n\n" + "\n\n".join(pdf_texts)
                    print(f"  ✓ Found {len(pdf_texts)} PDF attachment(s)")
                
                if not full_text.strip():
                    print("  ⚠ No text content found")
                    continue
                
                # Extract events using LLM (pass publication date for date inference)
                events = extract_events_with_llm(full_text, source=f"Email: {subject}", publication_date=pub_date)
                
                if events:
                    print(f"  ✓ Extracted {len(events)} events")
                    all_events.extend(events)
                else:
                    print("  ⚠ No events found")
                
                # Mark as processed
                processed_ids.append(email_id)
                stats['emails_processed'] += 1
                stats['events_extracted'] += len(events)
                
            except Exception as e:
                error_msg = f"Error processing email {email_id}: {str(e)}"
                print(f"  ✗ {error_msg}")
                stats['errors'].append(error_msg)
        
        # Insert all events to database (SQL only - no vector DB for events)
        if all_events:
            print(f"\nInserting {len(all_events)} events into database...")
            inserted = insert_events_to_db(all_events)
            stats['events_inserted'] = inserted
            print(f"✓ Inserted {inserted} events successfully")
        
        # Save updated sync state (keep last 1000 IDs to prevent file from growing too large)
        state['processed_email_ids'] = processed_ids[-1000:]
        save_email_sync_state(state)
        print("✓ Sync state saved")
        print("✓ Gmail API session completed")
        
    except Exception as e:
        error_msg = f"Fatal error during sync: {str(e)}"
        print(f"\n✗ {error_msg}")
        stats['errors'].append(error_msg)
    
    print("\n" + "=" * 80)
    print("Email Newsletter Sync Complete")
    print(f"Emails processed: {stats['emails_processed']}")
    print(f"Events extracted: {stats['events_extracted']}")
    print(f"Events inserted (SQL): {stats['events_inserted']}")
    print(f"Errors: {len(stats['errors'])}")
    print("=" * 80)
    
    return stats


if __name__ == "__main__":
    try:
        sync_email_newsletters_to_sql()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        sys.exit(1)

