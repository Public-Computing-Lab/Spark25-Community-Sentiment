#!/usr/bin/env python3
"""
Database Reset Script for Boston Data Sync

This script drops all tables and optionally recreates them from scratch.
Use this when you need to completely reset the database schema.

Usage:
    python reset_database.py                    # Drop all tables
    python reset_database.py --recreate         # Drop and recreate all tables
    python reset_database.py --recreate --sync  # Drop, recreate, and sync data
"""

import os
import sys
import json
import argparse
from pathlib import Path
import pymysql
from pymysql.cursors import DictCursor

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

# Default MySQL connection settings (can be overridden by environment variables)
MYSQL_CONFIG = {
    'host': os.getenv("MYSQL_HOST", "127.0.0.1"),
    'port': int(os.getenv("MYSQL_PORT", "3306")),
    'user': os.getenv("MYSQL_USER", "root"),
    'password': os.getenv("MYSQL_PASSWORD", ""),
    'database': os.getenv("MYSQL_DB", "rethink_ai_boston"),
    'charset': 'utf8mb4',
}


def load_config(config_file: Path) -> dict:
    """Load dataset configuration from JSON file."""
    if not config_file.exists():
        print(f"❌ Config file not found: {config_file}")
        sys.exit(1)
    
    with open(config_file, 'r') as f:
        return json.load(f)


def reset_database(config_file: Path, recreate: bool = False, sync: bool = False):
    """
    Drop all tables and optionally recreate them.
    
    Args:
        config_file: Path to dataset configuration JSON file
        recreate: If True, recreate tables after dropping
        sync: If True, sync data after recreating tables
    """
    print("="*60)
    print("🔄 Database Reset Script")
    print("="*60)
    
    # Load configuration
    config = load_config(config_file)
    
    # Get all table names from config
    tables_to_drop = []
    for dataset in config.get('datasets', []):
        table_name = dataset.get('table_name')
        if table_name:
            tables_to_drop.append(table_name)
    
    # Also drop filtered tables that might exist
    filtered_tables = ['shots_fired_data', 'homicide_data']
    all_tables = filtered_tables + [t for t in tables_to_drop if t not in filtered_tables]
    
    # Connect to MySQL
    try:
        conn = pymysql.connect(
            **MYSQL_CONFIG,
            cursorclass=DictCursor,
            autocommit=False
        )
        print(f"✅ Connected to MySQL: {MYSQL_CONFIG['database']}")
    except Exception as e:
        print(f"❌ MySQL connection failed: {e}")
        sys.exit(1)
    
    cursor = conn.cursor()
    
    try:
        # Check which tables exist
        print("\n📋 Checking existing tables...")
        existing_tables = []
        for table in all_tables:
            cursor.execute(f"SHOW TABLES LIKE '{table}'")
            if cursor.fetchone():
                existing_tables.append(table)
                print(f"   ✓ Found: {table}")
        
        if not existing_tables:
            print("   ℹ️  No tables found to drop")
            if recreate or sync:
                print("\n🔄 Creating tables from scratch...")
            else:
                conn.close()
                return
        
        # Drop tables in reverse dependency order (filtered tables first)
        print(f"\n🗑️  Dropping {len(existing_tables)} table(s)...")
        for table in existing_tables:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS `{table}`")
                print(f"   ✅ Dropped: {table}")
            except Exception as e:
                print(f"   ❌ Error dropping {table}: {e}")
                conn.rollback()
                raise
        
        conn.commit()
        print(f"\n✅ Successfully dropped {len(existing_tables)} table(s)")
        
        # Recreate tables if requested
        if recreate or sync:
            print("\n" + "="*60)
            print("🔄 Recreating Tables and Syncing Data")
            print("="*60)
            
            # Import and run the sync
            # Add current directory to path for import
            sys.path.insert(0, str(Path(__file__).parent))
            from boston_data_sync import BostonDataSyncer
            
            with BostonDataSyncer(config_file=str(config_file)) as syncer:
                # Force full sync (not incremental) after reset
                original_incremental = syncer.datasets_config['sync_settings'].get('incremental_sync', True)
                syncer.datasets_config['sync_settings']['incremental_sync'] = False
                
                try:
                    syncer.sync_all()
                finally:
                    # Restore original setting
                    syncer.datasets_config['sync_settings']['incremental_sync'] = original_incremental
        
        print("\n" + "="*60)
        print("✅ Database reset complete!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Error during reset: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Reset Boston Data Sync database - drop all tables',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Drop all tables
  python reset_database.py
  
  # Drop and recreate tables (then sync data)
  python reset_database.py --recreate --sync
  
  # Use custom config file
  python reset_database.py --config custom_config.json --recreate
        """
    )
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Path to config JSON file (default: boston_datasets_config.json)'
    )
    parser.add_argument(
        '--recreate',
        action='store_true',
        help='Recreate tables after dropping (requires --sync to also sync data)'
    )
    parser.add_argument(
        '--sync',
        action='store_true',
        help='Sync data after recreating tables (implies --recreate)'
    )
    parser.add_argument(
        '--confirm',
        action='store_true',
        help='Skip confirmation prompt (use with caution!)'
    )
    
    args = parser.parse_args()
    
    # Determine config file path
    if args.config:
        config_file = Path(args.config)
    else:
        config_file = Path(__file__).parent / "boston_datasets_config.json"
    
    if not config_file.exists():
        print(f"❌ Config file not found: {config_file}")
        sys.exit(1)
    
    # If --sync is used, also recreate
    if args.sync:
        args.recreate = True
    
    # Confirmation prompt
    if not args.confirm:
        print("\n⚠️  WARNING: This will DROP ALL TABLES in the database!")
        print(f"   Database: {MYSQL_CONFIG['database']}")
        print(f"   Tables to drop: All tables from {config_file.name}")
        
        if args.recreate:
            print("   Action: Drop tables and recreate them")
            if args.sync:
                print("   Action: Drop tables, recreate, and sync data")
        else:
            print("   Action: Drop tables only (no recreation)")
        
        response = input("\nAre you sure you want to continue? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("❌ Reset cancelled")
            sys.exit(0)
    
    # Run reset
    try:
        reset_database(config_file, recreate=args.recreate, sync=args.sync)
    except KeyboardInterrupt:
        print("\n\n❌ Reset interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Reset failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

