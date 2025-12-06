# Automated Data Ingestion System

This system automatically syncs data from multiple sources using a hybrid approach:
1. **Google Drive → Vector Database**: Client-uploaded documents (PDF, DOCX, TXT, MD)
2. **Email Newsletters → Hybrid Storage**:
   - **Events → MySQL Database**: Calendar events with dates/times for temporal queries
   - **Articles → Vector Database**: News stories and community updates for semantic search

Designed to run daily with minimal compute requirements (~$0.02-0.30/month in API costs).

## Features

✅ **Incremental sync** - Only processes new/changed files  
✅ **State tracking** - Remembers what's been processed  
✅ **Error resilient** - Continues despite individual failures  
✅ **Low compute** - Uses efficient models and batch operations  
✅ **Comprehensive logging** - Tracks all runs for monitoring  
✅ **Hybrid storage** - Best of both SQL and vector DB for different query types  

## Hybrid Storage Architecture

### Why Hybrid?

Different types of data work better with different storage systems:

**Events → MySQL (Structured)**
- Perfect for: "What events are happening this weekend?" "Show me all workshops in December"
- Efficient date range queries, filtering by time/location
- Fast aggregations and temporal analysis

**Articles/News → Vector DB (Unstructured)**
- Perfect for: "What's the latest news about affordable housing?" "Tell me about community safety initiatives"
- Semantic search finds relevant content by meaning, not just keywords
- Works with natural language queries

**Combined Queries**
- Your chatbot automatically uses both: "What events are this weekend and what's been happening in the community?"
- SQL for structured event data + Vector DB for contextual information

### What Goes Where?

| Content Type | Storage | Example Query |
|--------------|---------|---------------|
| Event listings with dates/times | MySQL | "Events on Saturday" |
| Community news articles | Vector DB | "Housing developments news" |
| Opinion pieces | Vector DB | "What do residents say about..." |
| Workshop schedules | MySQL | "Yoga classes this month" |
| Policy announcements | Vector DB | "New community programs" |
| Client-uploaded docs | Vector DB | "Find documents about X topic" |

### Configuration

Control article extraction in `.env`:
```bash
# Enable/disable article extraction (events always extracted)
EXTRACT_ARTICLES=true

# Minimum word count for articles (skip very short snippets)
ARTICLE_MIN_LENGTH=50
```

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

### 3. Gmail OAuth 2.0 Setup

**Important:** Gmail now requires OAuth 2.0 authentication (app-specific passwords were discontinued in November 2025).

#### Step 1: Enable Gmail API in Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or create a new one)
3. Navigate to **APIs & Services** > **Library**
4. Search for "Gmail API"
5. Click **Enable**

#### Step 2: Create OAuth 2.0 Credentials

1. In Google Cloud Console, go to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth client ID**
3. If prompted, configure the OAuth consent screen:
   - User Type: Select "External"
   - App name: "Newsletter Ingestion" (or any name)
   - User support email: Your email
   - Developer contact: Your email
   - Click **Save and Continue** through the steps
   - Add your email to "Test users"
4. Back in **Create OAuth client ID**:
   - Application type: **Desktop app**
   - Name: "Newsletter Ingestion Client"
   - Click **Create**
5. **IMPORTANT: Add Authorized Redirect URI**:
   - Click the pencil/edit icon next to your newly created OAuth client
   - Scroll down to **"Authorized redirect URIs"**
   - Click **"+ ADD URI"**
   - Add this exact URI: `http://localhost:8080/`
   - Click **Save**
   - **Wait 5 minutes** for Google to propagate the changes
6. **Download the JSON file**
   - Click the download icon next to your OAuth 2.0 Client ID
   - Save as `gmail_credentials.json` in the `data_ingestion/` folder

#### Step 3: No Additional Gmail Settings Needed

The Gmail API handles email access automatically - no need to enable IMAP or POP!

#### Step 4: First-Time Authentication

When you first run the ingestion script, it will:
1. Open your browser automatically
2. Ask you to sign in to your Gmail account
3. Show a warning "Google hasn't verified this app" - Click **Continue**
4. Grant permission to access Gmail
5. The script will save the token for future runs (no browser needed next time)

**Note:** The `gmail_token.json` file will be created automatically after first authentication.

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

# Email (Gmail OAuth 2.0)
NEWSLETTER_EMAIL_ADDRESS=your-email@gmail.com
GMAIL_CREDENTIALS_PATH=gmail_credentials.json
GMAIL_TOKEN_PATH=gmail_token.json

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

## Querying the Data

Once ingestion is running, you can query the data through your chatbot system:

### Events (SQL Queries)

Best for temporal, structured queries:
- "What events are happening this Saturday?"
- "Show me all workshops in December"  
- "List family activities next week"
- "Find events at the community center"

The SQL chatbot will automatically query the `weekly_events` table.

### Articles & Documents (Vector DB Queries)

Best for semantic, topic-based queries:
- "What's the latest news about affordable housing?"
- "Tell me about community safety initiatives"
- "What are people saying about the new development?"
- "Find information about youth programs"

The RAG system will search through:
- Client-uploaded documents
- Community news and announcements

### Hybrid Queries

The chatbot automatically combines both when appropriate:
- "What community events are this weekend, and what's been happening in local news?"
- "Are there any housing-related events coming up? Also, what recent articles discuss housing?"

### Filtering by Date

For articles in Vector DB, metadata includes `publication_date`:
- Recent articles can be prioritized in search results
- Can filter by date range if needed
- Useful for "latest news" type queries

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
├── email_to_calendar_sql.py      # Email sync script (OAuth 2.0)
├── main_daily_ingestion.py       # Main orchestrator
├── requirements.txt               # Python dependencies
├── env.example                    # Environment template
├── .env                          # Your configuration (not in git)
├── .gitignore                    # Git ignore rules
├── README.md                     # This file
├── gmail_credentials.json        # Gmail OAuth credentials (not in git)
├── gmail_token.json              # Gmail OAuth token (auto-generated, not in git)
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

### "Failed to connect to Gmail via OAuth"

**Solutions:**
- Ensure `gmail_credentials.json` exists in the `data_ingestion/` folder
- Check that Gmail API is enabled in Google Cloud Console
- Verify IMAP is enabled in Gmail settings
- Delete `gmail_token.json` and re-authenticate (the script will open a browser)
- Make sure your Gmail account is added to "Test users" in OAuth consent screen

### "Google hasn't verified this app" warning

This is normal when using your own OAuth credentials. Click **Continue** to proceed. Your app is private and only you can access it.

### Browser doesn't open for OAuth

If running on a server without a browser:
1. Run the script once locally on your computer
2. Complete the OAuth flow (browser will open)
3. Copy the generated `gmail_token.json` file to your server
4. The token will work without a browser going forward

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

