"""
Main Daily Ingestion Script
Orchestrates Google Drive, Email, and Boston Open Data ingestion processes.
Run this script once per day via cron job or task scheduler.
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import json

# Import ingestion modules
from google_drive_to_vectordb import sync_google_drive_to_vectordb
from email_to_calendar_sql import sync_email_newsletters_to_sql
import config

# Import Boston data sync
from boston_data_sync.boston_data_sync import BostonDataSyncer

# Import dotnews downloader
from dotnews_downloader import download_latest_pdf

# Import newsletter processing function
from google_drive_to_vectordb import process_newsletter_pdf, insert_events_to_db

# Temporary: import vectordb builder from rag stuff (will be moved into this package later)
# Import directly from the rag stuff directory to avoid conflict with local build_vectordb.py
_RAG_STUFF_DIR = Path(__file__).parent.parent / "rag stuff"
if str(_RAG_STUFF_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_STUFF_DIR))

# Import using importlib to ensure we get the right module
import importlib.util
_vectordb_spec = importlib.util.spec_from_file_location(
    "rag_build_vectordb",
    _RAG_STUFF_DIR / "build_vectordb.py"
)
_vectordb_module = importlib.util.module_from_spec(_vectordb_spec)
_vectordb_spec.loader.exec_module(_vectordb_module)
build_vectordb = _vectordb_module.build_vectordb  # type: ignore

# Placeholder directories where future ingestion steps will drop files
INGESTION_POLICY_DIR = config.TEMP_DOWNLOAD_DIR / "policy_docs"
INGESTION_TRANSCRIPT_DIR = config.TEMP_DOWNLOAD_DIR / "transcripts"
INGESTION_NEWSLETTER_DIR = config.TEMP_DOWNLOAD_DIR / "newsletters"

for _d in (INGESTION_POLICY_DIR, INGESTION_TRANSCRIPT_DIR, INGESTION_NEWSLETTER_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def sync_dotnews_newsletters() -> dict:
    """
    Download and process the latest newsletter from dotnews.com.
    Returns stats dict with processing results.
    """
    stats = {
        'pdfs_downloaded': 0,
        'pdfs_processed': 0,
        'events_extracted': 0,
        'chunks_added': 0,
        'errors': []
    }
    
    try:
        # Download directory
        dotnews_dir = config.TEMP_DOWNLOAD_DIR / "dotnews"
        dotnews_dir.mkdir(parents=True, exist_ok=True)
        
        # Track processed files to avoid re-processing
        processed_file = dotnews_dir / ".processed_dotnews.json"
        processed_files = {}
        if processed_file.exists():
            try:
                processed_files = json.loads(processed_file.read_text())
            except:
                processed_files = {}
        
        # Download latest PDF
        print("  📥 Downloading latest newsletter from dotnews.com...")
        pdf_path = download_latest_pdf(output_dir=dotnews_dir)
        
        if not pdf_path:
            print("  ⚠ No PDF downloaded (may already be latest or download failed)")
            return stats
        
        stats['pdfs_downloaded'] = 1
        
        # Check if we've already processed this file
        file_key = pdf_path.name
        if file_key in processed_files:
            print(f"  ✓ Already processed: {file_key}")
            return stats
        
        # Process the newsletter PDF
        print(f"  📰 Processing: {pdf_path.name}")
        file_metadata = {
            'name': pdf_path.name,
            'id': f'dotnews_{pdf_path.name}',
            'modifiedTime': datetime.fromtimestamp(pdf_path.stat().st_mtime).isoformat() + 'Z'
        }
        
        result = process_newsletter_pdf(pdf_path, file_metadata)
        
        # Insert events into database
        if result.get('events'):
            events_inserted = insert_events_to_db(result['events'])
            stats['events_extracted'] = len(result['events'])
            print(f"  ✓ Inserted {events_inserted} events into database")
        
        # Add documents to vector DB (will be handled in Phase 4)
        stats['chunks_added'] = len(result.get('documents', []))
        stats['pdfs_processed'] = 1
        
        # Mark as processed
        processed_files[file_key] = {
            'name': pdf_path.name,
            'processed_at': datetime.now().isoformat(),
            'chunks': len(result.get('documents', [])),
            'events': len(result.get('events', []))
        }
        
        # Save processed files list (keep only last 10 to avoid file growing)
        if len(processed_files) > 10:
            # Keep only the most recent 10
            sorted_files = sorted(processed_files.items(), key=lambda x: x[1].get('processed_at', ''), reverse=True)
            processed_files = dict(sorted_files[:10])
        
        processed_file.write_text(json.dumps(processed_files, indent=2))
        
    except Exception as e:
        error_msg = f"Error syncing dotnews: {e}"
        print(f"  ✗ {error_msg}")
        stats['errors'].append(error_msg)
    
    return stats


def log_run_summary(drive_stats: dict, email_stats: dict, boston_stats: dict = None, dotnews_stats: dict = None) -> None:
    """Log summary of the ingestion run to a JSONL file."""
    log_file = Path(__file__).parent / "ingestion_log.jsonl"
    
    summary = {
        "timestamp": datetime.now().isoformat(),
        "google_drive": drive_stats,
        "email_newsletters": email_stats,
    }
    
    if boston_stats:
        summary["boston_open_data"] = boston_stats
    
    if dotnews_stats:
        summary["dotnews"] = dotnews_stats
    
    # Calculate overall success
    errors = (
        len(drive_stats.get('errors', [])) + 
        len(email_stats.get('errors', [])) +
        (sum(len(d.get('errors', [])) for d in boston_stats.get('datasets', [])) if boston_stats else 0) +
        len(dotnews_stats.get('errors', [])) if dotnews_stats else 0
    )
    summary["success"] = errors == 0
    
    # Append to log file (JSONL format - one JSON object per line)
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(summary) + "\n")
        print(f"\n📝 Run summary logged to {log_file}")
    except Exception as e:
        print(f"\n⚠ Warning: Could not write to log file: {e}")


def print_banner(title: str) -> None:
    """Print a formatted banner."""
    width = 80
    print("\n" + "╔" + "=" * (width - 2) + "╗")
    padding = (width - len(title) - 2) // 2
    print("║" + " " * padding + title + " " * (width - padding - len(title) - 2) + "║")
    print("╚" + "=" * (width - 2) + "╝\n")


def print_final_summary(drive_stats: dict, email_stats: dict, boston_stats: dict = None, dotnews_stats: dict = None) -> None:
    """Print final summary of the ingestion run."""
    drive_errors = len(drive_stats.get('errors', []))
    email_errors = len(email_stats.get('errors', []))
    boston_errors = sum(len(d.get('errors', [])) for d in boston_stats.get('datasets', [])) if boston_stats else 0
    total_errors = drive_errors + email_errors + boston_errors
    
    print("\n╔" + "=" * 78 + "╗")
    print("║" + " " * 30 + "FINAL SUMMARY" + " " * 35 + "║")
    print("╠" + "=" * 78 + "╣")
    
    # Google Drive stats
    files = drive_stats.get('files_processed', 0)
    chunks = drive_stats.get('chunks_added', 0)
    print(f"║ Google Drive Files Processed: {files:>5}                                      ║")
    print(f"║ Vector DB Chunks Added:       {chunks:>5}                                      ║")
    
    # Email stats
    emails = email_stats.get('emails_processed', 0)
    events_sql = email_stats.get('events_inserted', 0)
    print(f"║ Emails Processed:             {emails:>5}                                      ║")
    print(f"║ Calendar Events (SQL):        {events_sql:>5}                                      ║")
    
    # Boston Open Data stats
    if boston_stats:
        datasets = boston_stats.get('datasets_synced', 0)
        records = boston_stats.get('total_records', 0)
        duration = boston_stats.get('duration_seconds', 0)
        print(f"║ Boston Datasets Synced:        {datasets:>5}                                      ║")
        print(f"║ Boston Records Synced:         {records:>5}                                      ║")
        if duration > 0:
            print(f"║ Boston Sync Duration:           {duration:>5.1f}s                                    ║")
    
    # Dotnews stats
    if dotnews_stats:
        pdfs = dotnews_stats.get('pdfs_processed', 0)
        events = dotnews_stats.get('events_extracted', 0)
        chunks = dotnews_stats.get('chunks_added', 0)
        print(f"║ Dotnews PDFs Processed:        {pdfs:>5}                                      ║")
        print(f"║ Dotnews Events Extracted:      {events:>5}                                      ║")
        print(f"║ Dotnews Chunks Added:          {chunks:>5}                                      ║")
    
    # Total errors
    print(f"║ Total Errors:                 {total_errors:>5}                                      ║")
    
    print("╚" + "=" * 78 + "╝\n")
    
    # Status message
    if total_errors == 0:
        print("✅ Daily ingestion completed successfully!\n")
    else:
        print(f"⚠️  Daily ingestion completed with {total_errors} error(s).\n")
        print("Error details:")
        for error in drive_stats.get('errors', []):
            print(f"  - [Google Drive] {error}")
        for error in email_stats.get('errors', []):
            print(f"  - [Email] {error}")
        if boston_stats:
            for dataset in boston_stats.get('datasets', []):
                for error in dataset.get('errors', []):
                    print(f"  - [Boston Data: {dataset.get('dataset', 'unknown')}] {error}")
        for error in dotnews_stats.get('errors', []) if dotnews_stats else []:
            print(f"  - [Dotnews] {error}")
        print()


def main():
    """Run daily data ingestion for all sources."""
    print_banner(f"DAILY DATA INGESTION RUN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Print configuration summary if verbose
    if config.VERBOSE_LOGGING:
        config.print_config_summary()
    
    # Run Dotnews download and processing
    print("\n" + "►" * 40)
    print("► PHASE 0: Dotnews Newsletter Download & Processing")
    print("►" * 40)
    
    try:
        dotnews_stats = sync_dotnews_newsletters()
    except Exception as e:
        print(f"\n✗ FATAL: Dotnews sync failed: {e}")
        dotnews_stats = {
            "pdfs_downloaded": 0,
            "pdfs_processed": 0,
            "events_extracted": 0,
            "chunks_added": 0,
            "errors": [str(e)]
        }
    
    # Separator
    print("\n" + "-" * 80 + "\n")
    
    # Run Google Drive sync
    print("►" * 40)
    print("► PHASE 1: Google Drive → Vector DB")
    print("►" * 40)
    
    try:
        drive_stats = sync_google_drive_to_vectordb()
    except Exception as e:
        print(f"\n✗ FATAL: Google Drive sync failed: {e}")
        drive_stats = {
            "files_processed": 0,
            "chunks_added": 0,
            "errors": [str(e)]
        }
    
    # Separator
    print("\n" + "-" * 80 + "\n")
    
    # Run Email sync
    print("►" * 40)
    print("► PHASE 2: Email Newsletter → Calendar SQL")
    print("►" * 40)
    
    try:
        email_stats = sync_email_newsletters_to_sql()
    except Exception as e:
        print(f"\n✗ FATAL: Email sync failed: {e}")
        email_stats = {
            "emails_processed": 0,
            "events_extracted": 0,
            "events_inserted": 0,
            "articles_extracted": 0,
            "articles_added": 0,
            "errors": [str(e)]
        }
    
    # Separator
    print("\n" + "-" * 80 + "\n")
    
    # Run Boston Open Data sync
    print("►" * 40)
    print("► PHASE 3: Boston Open Data → MySQL")
    print("►" * 40)
    
    boston_stats = None
    try:
        with BostonDataSyncer() as syncer:
            boston_stats = syncer.sync_all()
    except Exception as e:
        print(f"\n✗ FATAL: Boston data sync failed: {e}")
        boston_stats = {
            "datasets_synced": 0,
            "total_records": 0,
            "datasets": [{
                "dataset": "unknown",
                "errors": [str(e)]
            }]
        }
    
    # Separator
    print("\n" + "-" * 80 + "\n")
    
    # After ingestion, update the unified vector DB from any files present
    # in the placeholder directories. Future steps will copy the right files
    # into these folders before this runs.
    print("►" * 40)
    print("► PHASE 4: Building/Updating Vector DB")
    print("►" * 40)
    
    try:
        build_vectordb(
            policy_dir=INGESTION_POLICY_DIR,
            transcript_dir=INGESTION_TRANSCRIPT_DIR,
            newsletter_dir=INGESTION_NEWSLETTER_DIR,
        )
    except Exception as e:
        print(f"\n⚠️  Vectordb build/update failed: {e}")
    
    # Log summary
    log_run_summary(drive_stats, email_stats, boston_stats, dotnews_stats)
    
    # Print final summary
    print_final_summary(drive_stats, email_stats, boston_stats, dotnews_stats)
    
    # Exit with error code if there were failures
    drive_errors = len(drive_stats.get('errors', []))
    email_errors = len(email_stats.get('errors', []))
    boston_errors = sum(len(d.get('errors', [])) for d in boston_stats.get('datasets', [])) if boston_stats else 0
    dotnews_errors = len(dotnews_stats.get('errors', [])) if dotnews_stats else 0
    total_errors = drive_errors + email_errors + boston_errors + dotnews_errors
    
    if total_errors > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Exiting...")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        print(f"\n\n✗ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

