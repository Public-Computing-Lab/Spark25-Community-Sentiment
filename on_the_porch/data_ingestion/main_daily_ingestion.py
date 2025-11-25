"""
Main Daily Ingestion Script
Orchestrates both Google Drive and Email ingestion processes.
Run this script once per day via cron job or task scheduler.
"""
import sys
from pathlib import Path
from datetime import datetime
import json

# Import ingestion modules
from google_drive_to_vectordb import sync_google_drive_to_vectordb
from email_to_calendar_sql import sync_email_newsletters_to_sql
import config


def log_run_summary(drive_stats: dict, email_stats: dict) -> None:
    """Log summary of the ingestion run to a JSONL file."""
    log_file = Path(__file__).parent / "ingestion_log.jsonl"
    
    summary = {
        "timestamp": datetime.now().isoformat(),
        "google_drive": drive_stats,
        "email_newsletters": email_stats,
        "success": len(drive_stats.get('errors', [])) == 0 and len(email_stats.get('errors', [])) == 0
    }
    
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


def print_final_summary(drive_stats: dict, email_stats: dict) -> None:
    """Print final summary of the ingestion run."""
    total_errors = len(drive_stats.get('errors', [])) + len(email_stats.get('errors', []))
    
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
    events_vectordb = email_stats.get('events_vectordb_added', 0)
    articles = email_stats.get('articles_added', 0)
    print(f"║ Emails Processed:             {emails:>5}                                      ║")
    print(f"║ Calendar Events (SQL):        {events_sql:>5}                                      ║")
    print(f"║ Calendar Events (Vector DB):  {events_vectordb:>5}                                      ║")
    if config.EXTRACT_ARTICLES:
        print(f"║ Newsletter Articles Added:    {articles:>5}                                      ║")
    
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
        print()


def main():
    """Run daily data ingestion for both sources."""
    print_banner(f"DAILY DATA INGESTION RUN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Print configuration summary if verbose
    if config.VERBOSE_LOGGING:
        config.print_config_summary()
    
    # Run Google Drive sync
    print("\n" + "►" * 40)
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
    
    # Log summary
    log_run_summary(drive_stats, email_stats)
    
    # Print final summary
    print_final_summary(drive_stats, email_stats)
    
    # Exit with error code if there were failures
    total_errors = len(drive_stats.get('errors', [])) + len(email_stats.get('errors', []))
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

