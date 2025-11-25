"""
Email Newsletter to Calendar SQL Ingestion
Reads newsletters from a dedicated email inbox and extracts events to SQL database.
"""
import imaplib
import json
import sys
from pathlib import Path
from typing import List, Dict
from datetime import datetime, timedelta

# LLM for extraction
import google.generativeai as genai

# Local imports
sys.path.insert(0, str(Path(__file__).parent.parent))
import sql_chat.app4 as app4

import config
from utils.email_parser import (
    extract_text_from_email,
    extract_pdf_attachments,
    get_email_subject
)


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


def connect_to_email() -> imaplib.IMAP4_SSL:
    """Connect to email server via IMAP."""
    if not config.EMAIL_ADDRESS or not config.EMAIL_PASSWORD:
        raise ValueError("Email credentials not configured")
    
    try:
        mail = imaplib.IMAP4_SSL(config.IMAP_SERVER, config.IMAP_PORT)
        mail.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
        return mail
    except Exception as e:
        raise RuntimeError(f"Failed to connect to email server: {e}")


def get_recent_newsletters(mail: imaplib.IMAP4_SSL, processed_ids: List[str], days_back: int = 7) -> List[tuple]:
    """
    Fetch recent newsletters that haven't been processed.
    Returns list of (email_id, email_message) tuples.
    """
    # Select inbox
    mail.select("inbox")
    
    # Search for emails from the last N days
    since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
    
    try:
        status, messages = mail.search(None, f'(SINCE {since_date})')
    except Exception as e:
        raise RuntimeError(f"Failed to search emails: {e}")
    
    if status != "OK":
        return []
    
    email_ids = messages[0].split()
    
    newsletters = []
    for email_id in email_ids:
        email_id_str = email_id.decode()
        
        # Skip if already processed
        if email_id_str in processed_ids:
            continue
        
        # Fetch email
        try:
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                continue
            
            # Parse email
            import email
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            newsletters.append((email_id_str, msg))
        except Exception:
            continue
    
    return newsletters


def extract_events_with_llm(text: str, source: str) -> List[Dict]:
    """Use LLM to extract structured events from newsletter text."""
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured")
    
    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(config.GEMINI_MODEL)
    
    # Truncate very long text to avoid token limits
    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... text truncated ...]"
    
    prompt = f"""
You are reading a community newsletter or calendar listing events.

Extract ALL events with their dates and times from the text below.

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
- "event_date": Date label as written (e.g., "Monday", "June 3-5", "All week")
- "start_date": ISO date YYYY-MM-DD when event starts (or null)
- "end_date": ISO date YYYY-MM-DD when event ends (or null if same day)
- "start_time": 24-hour time HH:MM (or null)
- "end_time": 24-hour time HH:MM (or null)
- "raw_text": Original text describing the event
- "location": Where the event takes place (or null)

Be conservative: only extract clear events with dates. Never invent information.

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
        
        # Connect to email
        print("Connecting to email server...")
        mail = connect_to_email()
        print("✓ Connected successfully")
        
        # Get recent newsletters
        print(f"Scanning inbox for newsletters from last {config.EMAIL_LOOKBACK_DAYS} days...")
        newsletters = get_recent_newsletters(mail, processed_ids, days_back=config.EMAIL_LOOKBACK_DAYS)
        
        print(f"Found {len(newsletters)} new newsletters to process.")
        
        if not newsletters:
            print("No new newsletters. Exiting.")
            mail.logout()
            return stats
        
        all_events = []
        
        # Process each newsletter
        for i, (email_id, msg) in enumerate(newsletters, 1):
            try:
                # Get subject
                subject = get_email_subject(msg)
                
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
                
                # Extract events using LLM
                events = extract_events_with_llm(full_text, source=f"Email: {subject}")
                
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
        
        # Insert all events to database
        if all_events:
            print(f"\nInserting {len(all_events)} events into database...")
            inserted = insert_events_to_db(all_events)
            stats['events_inserted'] = inserted
            print(f"✓ Inserted {inserted} events successfully")
        
        # Save updated sync state (keep last 1000 IDs to prevent file from growing too large)
        state['processed_email_ids'] = processed_ids[-1000:]
        save_email_sync_state(state)
        print("✓ Sync state saved")
        
        # Logout
        mail.logout()
        print("✓ Disconnected from email server")
        
    except Exception as e:
        error_msg = f"Fatal error during sync: {str(e)}"
        print(f"\n✗ {error_msg}")
        stats['errors'].append(error_msg)
    
    print("\n" + "=" * 80)
    print("Email Newsletter Sync Complete")
    print(f"Emails processed: {stats['emails_processed']}")
    print(f"Events extracted: {stats['events_extracted']}")
    print(f"Events inserted: {stats['events_inserted']}")
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

