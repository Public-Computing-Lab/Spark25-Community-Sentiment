# Boston Open Data Portal → MySQL Automated Sync

This automation system syncs data from [data.boston.gov](https://data.boston.gov) to your local MySQL server. It supports incremental updates, multiple datasets, and can be scheduled to run automatically.

## Features

- ✅ **Automated syncing** from Boston's CKAN API
- ✅ **Incremental updates** - only syncs new/changed records
- ✅ **Multiple datasets** - configure and sync multiple datasets
- ✅ **Automatic table creation** - creates MySQL tables with proper schema
- ✅ **Error handling** - robust error handling and logging
- ✅ **Scheduling support** - easy integration with cron/Task Scheduler

## Quick Start

### 1. Install Dependencies

Make sure you have the required packages:

```bash
pip install pandas requests pymysql
```

Or install from the parent requirements file:

```bash
cd ..
pip install -r requirements.txt
```

### 2. Configure MySQL Connection

Set environment variables for your MySQL connection:

```bash
# Windows PowerShell
$env:MYSQL_HOST="127.0.0.1"
$env:MYSQL_PORT="3306"
$env:MYSQL_USER="root"
$env:MYSQL_PASSWORD="your_password"
$env:MYSQL_DB="rethink_ai_boston"

# Linux/Mac
export MYSQL_HOST="127.0.0.1"
export MYSQL_PORT="3306"
export MYSQL_USER="root"
export MYSQL_PASSWORD="your_password"
export MYSQL_DB="rethink_ai_boston"
```

Or create a `.env` file in the parent `data_ingestion` directory.

### 3. Configure Datasets

Edit `boston_datasets_config.json` to configure which datasets to sync:

```json
{
  "datasets": [
    {
      "name": "crime_incident_reports",
      "resource_id": "b973d8cb-eeb2-4e7e-99da-c92938efc9c0",
      "table_name": "crime_incident_reports",
      "primary_key": "INCIDENT_NUMBER",
      "date_field": "OCCURRED_ON_DATE",
      "description": "Crime incident reports",
      "enabled": true
    }
  ],
  "sync_settings": {
    "batch_size": 5000,
    "max_records_per_sync": 100000,
    "rate_limit_delay": 1.0,
    "incremental_sync": true,
    "days_to_sync": 30
  }
}
```

#### Finding Resource IDs

Use the helper script to find resource IDs:

```bash
python find_boston_resource_id.py "crime incident reports"
```

### 4. Run the Sync

**Sync all enabled datasets:**
```bash
python boston_data_sync.py
```

**Sync a specific dataset:**
```bash
python boston_data_sync.py --dataset crime_incident_reports
```

**Do a full sync (not incremental):**
```bash
python boston_data_sync.py --full
```

**List configured datasets:**
```bash
python boston_data_sync.py --list-datasets
```

## Scheduling Automatic Updates

### Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (e.g., Daily at 2 AM)
4. Action: Start a program
5. Program: `python.exe`
6. Arguments: `"C:\path\to\boston_data_sync\schedule_boston_sync.py"`
7. Start in: `"C:\path\to\data_ingestion\boston_data_sync"`

### Linux/Mac Cron

Add to crontab (`crontab -e`):

```bash
# Run daily at 2 AM
0 2 * * * /usr/bin/python3 /path/to/boston_data_sync/schedule_boston_sync.py >> /path/to/boston_data_sync/sync.log 2>&1
```

## Files in This Directory

- `boston_data_sync.py` - Main sync script
- `boston_datasets_config.json` - Dataset configuration
- `schedule_boston_sync.py` - Scheduling wrapper
- `find_boston_resource_id.py` - Helper to find resource IDs
- `README.md` - This file

## Adding Future Years (2025, 2026, etc.)

When new 311 data becomes available for future years:

1. Find the resource ID:
   ```bash
   python find_boston_resource_id.py "311 service requests 2025"
   ```

2. Edit `boston_datasets_config.json` and update the placeholder entry:
   - Change `"resource_id"` from `"PLACEHOLDER_UPDATE_WHEN_AVAILABLE"` to the actual resource ID
   - Set `"enabled": true`
   - Update the description if needed

3. Or add a new entry for the new year following the same pattern.

## Automatic Filtered Tables

After syncing `crime_incident_reports`, the system automatically creates:
- **shots_fired_data** - Filtered from crime data where `shooting = 1`
- **homicide_data** - Filtered from crime data where `offense_description` contains 'HOMICIDE'

These tables are updated every time crime_incident_reports is synced.

## More Information

See the full documentation in `../BOSTON_DATA_SYNC_README.md` for detailed configuration options, troubleshooting, and advanced usage.

