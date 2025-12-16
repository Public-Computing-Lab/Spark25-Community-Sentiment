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

Or install from the requirements file:

```bash
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

Or create a `.env` file in the `data_ingestion` directory:

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=rethink_ai_boston
```

### 3. Configure Datasets

Edit `boston_data_sync/boston_datasets_config.json` to configure which datasets to sync:

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

To find the resource ID for a dataset:

1. Go to [data.boston.gov](https://data.boston.gov)
2. Navigate to the dataset you want
3. Click on a resource (data file)
4. The resource ID is in the URL or API endpoint
5. Or use the API: `https://data.boston.gov/api/3/action/package_show?id=<package_name>`

### 4. Run the Sync

**Sync all enabled datasets:**
```bash
cd boston_data_sync
python boston_data_sync.py
```

**Sync a specific dataset:**
```bash
cd boston_data_sync
python boston_data_sync.py --dataset crime_incident_reports
```

**Do a full sync (not incremental):**
```bash
cd boston_data_sync
python boston_data_sync.py --full
```

**List configured datasets:**
```bash
cd boston_data_sync
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

Or use PowerShell to create the task:

```powershell
$action = New-ScheduledTaskAction -Execute "python.exe" -Argument "C:\path\to\boston_data_sync\schedule_boston_sync.py" -WorkingDirectory "C:\path\to\data_ingestion\boston_data_sync"
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
Register-ScheduledTask -TaskName "Boston Data Sync" -Action $action -Trigger $trigger
```

### Linux/Mac Cron

Add to crontab (`crontab -e`):

```bash
# Run daily at 2 AM
0 2 * * * /usr/bin/python3 /path/to/boston_data_sync/schedule_boston_sync.py >> /path/to/boston_data_sync/sync.log 2>&1

# Run every 6 hours
0 */6 * * * /usr/bin/python3 /path/to/boston_data_sync/schedule_boston_sync.py >> /path/to/boston_data_sync/sync.log 2>&1
```

### Systemd Timer (Linux)

Create `/etc/systemd/system/boston-sync.service`:

```ini
[Unit]
Description=Boston Data Sync
After=network.target mysql.service

[Service]
Type=oneshot
User=your_user
WorkingDirectory=/path/to/data_ingestion/boston_data_sync
ExecStart=/usr/bin/python3 /path/to/data_ingestion/boston_data_sync/schedule_boston_sync.py
Environment="MYSQL_HOST=127.0.0.1"
Environment="MYSQL_USER=root"
Environment="MYSQL_PASSWORD=your_password"
Environment="MYSQL_DB=rethink_ai_boston"
```

Create `/etc/systemd/system/boston-sync.timer`:

```ini
[Unit]
Description=Boston Data Sync Timer

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
sudo systemctl enable boston-sync.timer
sudo systemctl start boston-sync.timer
```

## Configuration Options

### Dataset Configuration

Each dataset in `boston_data_sync/boston_datasets_config.json` has:

- **name**: Unique identifier for the dataset
- **resource_id**: CKAN resource ID from data.boston.gov
- **table_name**: MySQL table name (will be created if doesn't exist)
- **primary_key**: Column name to use as primary key
- **date_field**: Column name for date filtering (used in incremental sync)
- **description**: Human-readable description
- **enabled**: `true` to sync this dataset, `false` to skip

### Sync Settings

- **batch_size**: Number of records to insert per batch (default: 5000)
- **max_records_per_sync**: Maximum records to fetch per sync (default: 100000, set to null for unlimited)
- **rate_limit_delay**: Seconds to wait between API calls (default: 1.0)
- **incremental_sync**: If `true`, only syncs records newer than last sync (default: true)
- **days_to_sync**: For incremental sync, how many days back to check (default: 30)

## How It Works

1. **Fetch Data**: Uses Boston's CKAN API (`datastore_search`) to fetch data
2. **Incremental Sync**: Checks the latest date in your database and only fetches newer records
3. **Table Creation**: Automatically creates MySQL tables with appropriate data types
4. **Upsert**: Uses `INSERT ... ON DUPLICATE KEY UPDATE` to handle new and updated records
5. **Logging**: Saves sync statistics to `boston_sync_log.jsonl`

## Troubleshooting

### Connection Errors

If you get MySQL connection errors:

1. Verify MySQL is running: `mysql -u root -p`
2. Check environment variables are set correctly
3. Verify database exists: `CREATE DATABASE IF NOT EXISTS rethink_ai_boston;`
4. Check firewall/network settings

### API Errors

If the Boston API returns errors:

1. Check your internet connection
2. Verify the resource ID is correct
3. The API might be temporarily down - try again later
4. Check rate limiting - increase `rate_limit_delay` if needed

### Data Issues

If data isn't syncing correctly:

1. Check the sync log: `boston_sync_log.jsonl`
2. Run with `--full` to do a complete sync
3. Verify the `primary_key` and `date_field` are correct
4. Check MySQL table structure matches expected schema

### Finding More Datasets

To discover available datasets:

1. Visit https://data.boston.gov/organization/
2. Browse by organization or search
3. Click on a dataset to see its resources
4. Use the API explorer or check the resource URL for the resource ID

You can also use the helper script (if it exists):

```bash
python check_boston_datasets.py
```

## Integration with Existing System

This sync system can be integrated with your existing `main_daily_ingestion.py`:

```python
from boston_data_sync.boston_data_sync import BostonDataSyncer

# In your main ingestion function
def main():
    # ... existing code ...
    
    # Add Boston data sync
    print("\n" + "►" * 40)
    print("► PHASE 3: Boston Open Data → MySQL")
    print("►" * 40)
    
    try:
        with BostonDataSyncer() as syncer:
            boston_stats = syncer.sync_all()
            print(f"✅ Boston data sync: {boston_stats['datasets_synced']} datasets")
    except Exception as e:
        print(f"✗ Boston data sync failed: {e}")
```

## Example: Adding a New Dataset

1. Find the dataset on data.boston.gov
2. Get the resource ID from the dataset page (or use `find_boston_resource_id.py`)
3. Add to `boston_data_sync/boston_datasets_config.json`:

```json
{
  "name": "my_new_dataset",
  "resource_id": "abc123-def456-...",
  "table_name": "my_new_table",
  "primary_key": "id",
  "date_field": "created_date",
  "description": "My new dataset",
  "enabled": true
}
```

4. Run the sync: `cd boston_data_sync && python boston_data_sync.py --dataset my_new_dataset`

## Logs

- **Sync log**: `boston_data_sync/boston_sync_log.jsonl` - JSON lines with sync statistics
- **Scheduled log**: `boston_data_sync/boston_sync_scheduled.log` - Simple text log for scheduled runs

## Support

For issues or questions:
- Check the logs for error messages
- Verify your configuration file is valid JSON
- Ensure MySQL connection settings are correct
- Test with a single dataset first: `--dataset <name>`

