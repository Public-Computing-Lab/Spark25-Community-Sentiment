"""Standalone dotnews newsletter ingestion — bypasses main_daily_ingestion.py.

Downloads the latest PDF from dotnews.com, extracts events with Gemini,
and inserts them into the weekly_events table.
"""
import sys
from pathlib import Path
from datetime import datetime

# Make parent (on_the_porch) importable for sql_chat.app4
sys.path.insert(0, str(Path(__file__).parent.parent))
# Make current dir importable for config, utils, etc.
sys.path.insert(0, str(Path(__file__).parent))

import config
from dotnews_downloader import download_latest_pdf
from google_drive_to_vectordb import process_newsletter_pdf, insert_events_to_db


def main():
    dotnews_dir = config.TEMP_DOWNLOAD_DIR / "dotnews"
    dotnews_dir.mkdir(parents=True, exist_ok=True)

    print("📥 Downloading latest newsletter from dotnews.com...")
    pdf_path = download_latest_pdf(output_dir=dotnews_dir)
    if not pdf_path:
        print("✗ Download failed or no new PDF available")
        return 1

    print(f"📰 Processing: {pdf_path.name}")
    file_metadata = {
        'name': pdf_path.name,
        'id': f'dotnews_{pdf_path.name}',
        'modifiedTime': datetime.fromtimestamp(pdf_path.stat().st_mtime).isoformat() + 'Z',
    }

    result = process_newsletter_pdf(pdf_path, file_metadata)
    events = result.get('events', [])
    print(f"🔎 Extracted {len(events)} events from PDF")

    if events:
        inserted = insert_events_to_db(events)
        print(f"✓ Inserted {inserted} events into weekly_events")
    else:
        print("⚠ No events extracted — PDF may not contain a calendar section")

    return 0


if __name__ == "__main__":
    sys.exit(main())
