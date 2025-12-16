# DreamHost Deployment Guide

This directory contains scripts for deploying the RethinkAI application on DreamHost.

## Prerequisites

1. DreamHost account with SSH access
2. Python 3.11+ available on DreamHost
3. MySQL database (can be created via DreamHost panel)
4. Domain/subdomain configured for the application

## Quick Start

1. **Clone the repository** on your DreamHost server:
   ```bash
   cd ~
   git clone <repository-url> ml-misi-community-sentiment
   cd ml-misi-community-sentiment
   ```

2. **Run the setup script**:
   ```bash
   chmod +x scripts/dreamhost/setup.sh
   ./scripts/dreamhost/setup.sh
   ```

3. **Configure environment variables**:
   - Edit `api/.env` with your API keys and database credentials
   - Edit `on_the_porch/.env` with your configuration
   - Edit `on_the_porch/data_ingestion/.env` for data ingestion

4. **Set up the database**:
   ```bash
   chmod +x scripts/dreamhost/database_setup.sh
   ./scripts/dreamhost/database_setup.sh
   ```

5. **Deploy the application**:
   ```bash
   chmod +x scripts/dreamhost/deploy.sh
   ./scripts/dreamhost/deploy.sh
   ```

## Scripts

### setup.sh
Initial setup script that:
- Creates virtual environment
- Installs dependencies
- Creates necessary directories
- Sets up environment files from examples

### database_setup.sh
Database initialization script that:
- Tests database connection
- Creates database if needed
- Sets up required tables
- Creates indexes

### deploy.sh
Deployment script that:
- Updates dependencies
- Tests database connection
- Creates WSGI configuration
- Creates .htaccess for Passenger
- Generates cron job templates

## DreamHost Configuration

### Passenger Setup

1. In DreamHost panel, go to **Domains** → **Manage Domains**
2. Select your domain/subdomain
3. Enable **Passenger (Ruby/Node.js/Python apps)**
4. Set the web directory to your project root (or a symlink)

### File Permissions

```bash
# Set proper permissions
chmod 755 ~/ml-misi-community-sentiment
chmod 644 ~/ml-misi-community-sentiment/passenger_wsgi.py
chmod 644 ~/ml-misi-community-sentiment/.htaccess
```

### Environment Variables

DreamHost Passenger will automatically use your virtual environment if configured correctly. Make sure:
- `.htaccess` points to the correct Python path
- Environment variables are set in `.env` files
- Virtual environment is activated in `passenger_wsgi.py`

## Cron Jobs

The deployment script creates `run_daily_ingestion.sh` which runs the complete daily ingestion pipeline at 2 AM.

**Set up the cron job:**

**Option A: Via DreamHost Panel**
1. Go to **Goodies** → **Cron Jobs** in DreamHost panel
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

**What it does:**
- Downloads latest Dotnews newsletter
- Syncs Google Drive documents to vector database
- Syncs email newsletters (extracts events to MySQL)
- Syncs Boston Open Data (311 requests, 911 reports)
- Updates vector database with new documents

**Logs:**
- Check daily ingestion logs: `tail -f ~/ml-misi-community-sentiment/logs/daily_ingestion.log`
- Logs include timestamps, processing stats, and any errors

## Troubleshooting

### Application Not Loading

1. Check Passenger error logs in DreamHost panel
2. Verify Python version matches virtual environment
3. Check file permissions
4. Test database connection manually

### Database Connection Issues

1. Verify MySQL credentials in `.env`
2. Check MySQL host (may need to use `mysql.yourdomain.com` on DreamHost)
3. Ensure database exists and user has permissions

### Import Errors

1. Verify virtual environment is activated
2. Check that all dependencies are installed
3. Verify Python path in `.htaccess` and `passenger_wsgi.py`

### Logs

Check logs in:
- `~/ml-misi-community-sentiment/logs/` - Application logs
- DreamHost panel → **Goodies** → **Logs** - Web server logs
- DreamHost panel → **Domains** → **Passenger** - Passenger logs

## Production Checklist

- [ ] Environment variables configured in `.env` files
- [ ] Database initialized and populated
- [ ] API keys and secrets set
- [ ] File permissions set correctly
- [ ] Cron jobs configured
- [ ] SSL certificate installed (for HTTPS)
- [ ] `FLASK_SESSION_COOKIE_SECURE=True` in production
- [ ] Monitoring/logging set up
- [ ] Backup strategy in place

## Support

For issues:
1. Check logs first
2. Review DreamHost documentation
3. Contact DreamHost support if server-related
4. Check project README.md for general troubleshooting

