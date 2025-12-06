# DreamHost Quick Deploy Guide

**Just the commands. No extra info.**

## 1. SSH into DreamHost

```bash
ssh your-username@your-domain.com
```

## 2. Clone Repository

```bash
cd ~
git clone <repository-url> ml-misi-community-sentiment
cd ml-misi-community-sentiment
```

## 3. Run Setup

```bash
chmod +x scripts/dreamhost/setup.sh
./scripts/dreamhost/setup.sh
```

## 4. Configure Environment

Edit these files with your actual values:

```bash
nano api/.env
nano on_the_porch/.env
nano on_the_porch/data_ingestion/.env
```

Required values:
- `GEMINI_API_KEY` - Your Google Gemini API key
- `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB` - Database credentials
- `RETHINKAI_API_KEYS` - API authentication keys (comma-separated)
- `GOOGLE_DRIVE_FOLDER_ID` - Google Drive folder ID (if using)
- `NEWSLETTER_EMAIL_ADDRESS` - Email address (if using)
- `DATABASE_URL` - PostgreSQL connection (if using)

## 5. Setup Database

```bash
chmod +x scripts/dreamhost/database_setup.sh
./scripts/dreamhost/database_setup.sh
```

## 6. Deploy Application

```bash
chmod +x scripts/dreamhost/deploy.sh
./scripts/dreamhost/deploy.sh
```

## 7. Set Up Cron Job (Daily Ingestion at 2 AM)

**Option A: Via DreamHost Panel**
1. Go to **Goodies** → **Cron Jobs**
2. Add new cron job:
   - **Command**: `~/ml-misi-community-sentiment/scripts/dreamhost/run_daily_ingestion.sh`
   - **When to run**: `0 2 * * *` (2 AM daily)

**Option B: Via SSH**
```bash
crontab -e
```

Add this line:
```
0 2 * * * ~/ml-misi-community-sentiment/scripts/dreamhost/run_daily_ingestion.sh
```

Save and exit.

## 8. Configure DreamHost Domain

1. Go to **Domains** → **Manage Domains**
2. Select your domain/subdomain
3. Enable **Passenger (Ruby/Node.js/Python apps)**
4. Set web directory to: `~/ml-misi-community-sentiment` (or create symlink)

## 9. Test

```bash
# Test API locally
cd ~/ml-misi-community-sentiment/api
source ../venv/bin/activate
python api_v2.py
```

## 10. Check Logs

```bash
# Daily ingestion logs
tail -f ~/ml-misi-community-sentiment/logs/daily_ingestion.log

# Application logs (if any)
tail -f ~/ml-misi-community-sentiment/logs/api.log
```

## Troubleshooting

**Cron job not running?**
- Check script is executable: `chmod +x ~/ml-misi-community-sentiment/scripts/dreamhost/run_daily_ingestion.sh`
- Check cron logs: `tail -f ~/ml-misi-community-sentiment/logs/daily_ingestion.log`
- Verify cron is active: `crontab -l`

**API not working?**
- Check `.env` files have correct values
- Verify database connection: `./scripts/dreamhost/database_setup.sh`
- Check Passenger logs in DreamHost panel

**Import errors?**
- Activate venv: `source ~/ml-misi-community-sentiment/venv/bin/activate`
- Reinstall dependencies: `pip install -r ~/ml-misi-community-sentiment/requirements.txt`

