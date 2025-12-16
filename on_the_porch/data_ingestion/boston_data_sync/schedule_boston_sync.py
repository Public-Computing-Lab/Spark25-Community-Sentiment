#!/usr/bin/env python3
"""
Scheduling wrapper for Boston data sync.

This script can be used with:
- Windows Task Scheduler
- Linux/Mac cron
- Systemd timers
- Or run manually

Example cron entry (runs daily at 2 AM):
    0 2 * * * /path/to/python /path/to/schedule_boston_sync.py >> /path/to/sync.log 2>&1
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add this directory to path
sys.path.insert(0, str(Path(__file__).parent))

from boston_data_sync import BostonDataSyncer


def main():
    """Run the sync with error handling and logging."""
    script_dir = Path(__file__).parent
    log_file = script_dir / "boston_sync_scheduled.log"
    
    print(f"\n{'='*60}")
    print(f"🕐 Scheduled Boston Data Sync")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    try:
        with BostonDataSyncer() as syncer:
            stats = syncer.sync_all()
            
            # Log to file
            with open(log_file, 'a') as f:
                f.write(f"[{datetime.now().isoformat()}] Sync completed: "
                       f"{stats['datasets_synced']} datasets, "
                       f"{stats['total_records']} records\n")
            
            # Exit with error code if there were failures
            total_errors = sum(len(d.get('errors', [])) for d in stats['datasets'])
            if total_errors > 0:
                print(f"\n⚠️  Sync completed with {total_errors} error(s)")
                sys.exit(1)
            else:
                print("\n✅ Sync completed successfully")
                sys.exit(0)
    
    except Exception as e:
        error_msg = f"Fatal error during sync: {e}"
        print(f"\n❌ {error_msg}")
        
        # Log error
        with open(log_file, 'a') as f:
            f.write(f"[{datetime.now().isoformat()}] ERROR: {error_msg}\n")
        
        sys.exit(1)


if __name__ == "__main__":
    main()

