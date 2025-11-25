# Automated Data Ingestion System

This system automatically syncs data from two sources:
1. **Google Drive → Vector Database**: Client-uploaded documents (PDF, DOCX, TXT, MD)
2. **Email Newsletters → Calendar SQL**: Community event listings from email

Designed to run daily with minimal compute requirements (~$0.02-0.30/month in API costs).

## Features

✅ **Incremental sync** - Only processes new/changed files  
✅ **State tracking** - Remembers what's been processed  
✅ **Error resilient** - Continues despite individual failures  
✅ **Low compute** - Uses efficient models and batch operations  
✅ **Comprehensive logging** - Tracks all runs for monitoring  

## Prerequisites

### 1. Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Google Drive API Setup

#### Create a Service Account:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable **Google Drive API**:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google Drive API"
   - Click "Enable"
4. Create Service Account:
   - Navigate to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "Service Account"
   - Fill in service account details
   - Click "Create and Continue"
   - Skip optional steps (no roles needed for read-only)
5. Generate Key:
   - Click on the created service account
   - Go to "Keys" tab
   - Click "Add Key" > "Create new key"
   - Choose JSON format
   - Download the JSON file

#### Share Google Drive Folder:

1. Open your Google Drive folder where clients upload files
2. Click "Share"
3. Add the service account email (found in the JSON file as `client_email`)
4. Give it "Viewer" permission
5. Copy the folder ID from the URL:
   - URL format: `https://drive.google.com/drive/folders/[FOLDER_ID]`

### 3. Email Setup (Gmail)

#### Enable IMAP:

1. Go to Gmail Settings > "See all settings"
2. Click "Forwarding and POP/IMAP" tab
3. Enable IMAP
4. Save changes

#### Create App-Specific Password:

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable 2-Step Verification (if not already enabled)
3. Go to [App Passwords](https://myaccount.google.com/apppasswords)
4. Select "Mail" and "Other (custom name)"
5. Enter name like "Newsletter Ingestion"
6. Copy the generated 16-character password

**Note:** For non-Gmail providers, check their documentation for IMAP settings.

## Configuration

### 1. Copy Environment Template

```bash
cd on_the_porch/data_ingestion
cp env.example .env
```

### 2. Edit `.env` File

Fill in all required values:

```bash
# Google Drive
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
GOOGLE_CREDENTIALS_PATH=service_account_credentials.json

# Email
NEWSLETTER_EMAIL_ADDRESS=newsletters@yourdomain.com
NEWSLETTER_EMAIL_PASSWORD=your_16_char_app_password

# Paths (defaults are usually fine)
VECTORDB_DIR=../vectordb_new
TEMP_DOWNLOAD_DIR=./temp_downloads

# Database & AI (from existing setup)
DATABASE_URL=your_database_connection_string
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash-exp
```

### 3. Place Credentials File

Put your Google service account JSON file in this directory as:
```
on_the_porch/data_ingestion/service_account_credentials.json
```

(Or update `GOOGLE_CREDENTIALS_PATH` in `.env` to point to a different location)

## Usage

### Test Individual Components

#### Test Configuration:
```bash
python config.py
```
This validates all settings and shows what's configured.

#### Test Google Drive Sync:
```bash
python google_drive_to_vectordb.py
```

#### Test Email Sync:
```bash
python email_to_calendar_sql.py
```

### Run Full Daily Ingestion

```bash
python main_daily_ingestion.py
```

This runs both sync processes and logs results to `ingestion_log.jsonl`.

## Scheduling

### Linux/Mac (cron)

1. Edit crontab:
```bash
crontab -e
```

2. Add daily run at 2 AM:
```bash
0 2 * * * cd /path/to/on_the_porch/data_ingestion && /path/to/python main_daily_ingestion.py >> logs/cron.log 2>&1
```

3. Create logs directory:
```bash
mkdir logs
```

### Windows (Task Scheduler)

1. Create batch script `run_daily_ingestion.bat`:
```batch
@echo off
cd C:\path\to\on_the_porch\data_ingestion
C:\path\to\python.exe main_daily_ingestion.py >> logs\cron.log 2>&1
```

2. Open Task Scheduler
3. Create Basic Task:
   - Name: "Daily Data Ingestion"
   - Trigger: Daily at 2:00 AM
   - Action: Start a program
   - Program: `C:\path\to\run_daily_ingestion.bat`

## Monitoring

### Check Logs

View recent ingestion runs:
```bash
tail -n 50 ingestion_log.jsonl
```

View formatted (requires `jq`):
```bash
cat ingestion_log.jsonl | jq '.'
```

### Check Sync State

```bash
# Google Drive sync state
cat .sync_state.json | jq '.'

# Email sync state
cat .email_sync_state.json | jq '.'
```

## File Structure

```
data_ingestion/
├── config.py                      # Configuration loader
├── google_drive_to_vectordb.py   # Google Drive sync script
├── email_to_calendar_sql.py      # Email sync script
├── main_daily_ingestion.py       # Main orchestrator
├── requirements.txt               # Python dependencies
├── env.example                    # Environment template
├── .env                          # Your configuration (not in git)
├── .gitignore                    # Git ignore rules
├── README.md                     # This file
├── utils/
│   ├── __init__.py
│   ├── document_processor.py     # Document parsing utilities
│   └── email_parser.py           # Email parsing utilities
├── temp_downloads/               # Temporary file downloads
├── .sync_state.json             # Google Drive sync state
├── .email_sync_state.json       # Email sync state
└── ingestion_log.jsonl          # Run history log
```

## Troubleshooting

### "Google credentials file not found"

**Solution:** Ensure the JSON file path in `.env` is correct and the file exists.

### "Failed to connect to email server"

**Solutions:**
- Verify email address and password in `.env`
- For Gmail: Ensure you're using an app-specific password (not your regular password)
- Check IMAP is enabled in Gmail settings
- Verify IMAP server and port settings

### "GOOGLE_DRIVE_FOLDER_ID is not set"

**Solution:** Add the folder ID to `.env`. Get it from the Google Drive URL.

### "No new files to process"

This is normal if there haven't been any uploads since last run. The system tracks what's already been processed.

### "Database connection error"

**Solution:** Verify `DATABASE_URL` in `.env` is correct and the database is accessible.

### High API Costs

**Solutions:**
- Reduce `EMAIL_LOOKBACK_DAYS` (default: 7)
- Set `MAX_FILES_PER_RUN` lower (default: 100)
- Use `gemini-2.0-flash-exp` or flash-lite models (cheapest)

## Cost Optimization

The system is designed for minimal costs:

| Component | Cost |
|-----------|------|
| Google Drive API | **FREE** (well within free tier) |
| Gmail IMAP | **FREE** |
| Vector DB (Chroma) | **FREE** (runs locally) |
| Database | **$0** (existing) |
| Gemini API | **~$0.02-0.30/month** (only real cost) |

**Total: < $1/month**

### Reduce Costs Further:

1. Process fewer emails: Lower `EMAIL_LOOKBACK_DAYS`
2. Limit file processing: Set `MAX_FILES_PER_RUN`
3. Use cheaper model: `gemini-2.0-flash-exp`
4. Enable verbose logging only when debugging: `VERBOSE_LOGGING=false`

## Support

For issues or questions, refer to:
- Google Drive API: https://developers.google.com/drive/api/v3/about-sdk
- Gmail IMAP: https://support.google.com/mail/answer/7126229
- Gemini API: https://ai.google.dev/docs

## Security Notes

⚠️ **Important:**
- Never commit `.env` file to git (it's in `.gitignore`)
- Keep service account JSON file secure
- Use app-specific passwords for email (not your main password)
- Regularly rotate credentials
- Use read-only permissions where possible

## License

Part of the ml-misi-community-sentiment project.

