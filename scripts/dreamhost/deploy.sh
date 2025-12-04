#!/bin/bash
# DreamHost Deployment Script
# This script deploys the RethinkAI application to DreamHost

set -e  # Exit on error

echo "=========================================="
echo "RethinkAI DreamHost Deployment"
echo "=========================================="

# Configuration
PROJECT_DIR="$HOME/ml-misi-community-sentiment"
VENV_DIR="$PROJECT_DIR/venv"
API_DIR="$PROJECT_DIR/api"
LOG_DIR="$PROJECT_DIR/logs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    print_error "Project directory not found: $PROJECT_DIR"
    print_error "Please run setup.sh first or clone the repository"
    exit 1
fi

# Activate virtual environment
if [ ! -d "$VENV_DIR" ]; then
    print_error "Virtual environment not found. Please run setup.sh first"
    exit 1
fi

source "$VENV_DIR/bin/activate"
print_status "Virtual environment activated"

# Update dependencies
print_status "Updating dependencies..."
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    pip install -r "$PROJECT_DIR/requirements.txt" --quiet
else
    print_error "requirements.txt not found in project root!"
    exit 1
fi

# Check environment files
print_warning "Checking environment configuration..."
if [ ! -f "$PROJECT_DIR/api/.env" ]; then
    print_error "api/.env not found. Please create it from .env.example"
    exit 1
fi

# Create log directory
mkdir -p "$LOG_DIR"

# Test database connection
print_status "Testing database connection..."
cd "$API_DIR"
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
import pymysql
try:
    conn = pymysql.connect(
        host=os.getenv('MYSQL_HOST', '127.0.0.1'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER', 'root'),
        password=os.getenv('MYSQL_PASSWORD', ''),
        database=os.getenv('MYSQL_DB', 'rethink_ai_boston')
    )
    conn.close()
    print('Database connection successful')
except Exception as e:
    print(f'Database connection failed: {e}')
    exit(1)
" || {
    print_error "Database connection test failed"
    exit 1
}

# Create WSGI file for DreamHost
print_status "Creating WSGI configuration..."
WSGI_FILE="$PROJECT_DIR/passenger_wsgi.py"
cat > "$WSGI_FILE" <<EOF
import sys
import os
from pathlib import Path

# Add project to path
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "api"))
sys.path.insert(0, str(PROJECT_DIR / "on_the_porch"))
sys.path.insert(0, str(PROJECT_DIR / "on_the_porch" / "rag stuff"))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(PROJECT_DIR / "api" / ".env")
load_dotenv(PROJECT_DIR / "on_the_porch" / ".env")

# Import and configure application
from api.api_v2 import app, _bootstrap_env, _fix_retrieval_vectordb_path, ensure_interaction_log_table

# Bootstrap environment
_bootstrap_env()
_fix_retrieval_vectordb_path()
ensure_interaction_log_table()

# DreamHost Passenger expects 'application'
application = app

if __name__ == "__main__":
    app.run()
EOF

chmod 644 "$WSGI_FILE"
print_status "WSGI file created: $WSGI_FILE"

# Create .htaccess for DreamHost Passenger
print_status "Creating .htaccess file..."
HTACCESS_FILE="$PROJECT_DIR/.htaccess"
cat > "$HTACCESS_FILE" <<EOF
PassengerEnabled On
PassengerAppRoot $PROJECT_DIR
PassengerPython $VENV_DIR/bin/python
PassengerBaseURI /
EOF

chmod 644 "$HTACCESS_FILE"
print_status ".htaccess file created"

# Create daily ingestion cron script
print_status "Creating daily ingestion cron script..."
CRON_SCRIPT="$PROJECT_DIR/scripts/dreamhost/run_daily_ingestion.sh"
cat > "$CRON_SCRIPT" <<'SCRIPT_EOF'
#!/bin/bash
# Daily Ingestion Cron Job Script
# Runs the complete daily ingestion pipeline at 2 AM

set -e  # Exit on error

# Configuration
PROJECT_DIR="$HOME/ml-misi-community-sentiment"
VENV_DIR="$PROJECT_DIR/venv"
INGESTION_DIR="$PROJECT_DIR/on_the_porch/data_ingestion"
LOG_DIR="$PROJECT_DIR/logs"
SCRIPT_LOG="$LOG_DIR/daily_ingestion.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Change to ingestion directory
cd "$INGESTION_DIR"

# Load environment variables from .env file
if [ -f "$INGESTION_DIR/.env" ]; then
    set -a
    source "$INGESTION_DIR/.env"
    set +a
fi

# Run the main daily ingestion script
echo "==========================================" >> "$SCRIPT_LOG"
echo "Daily Ingestion Started: $(date)" >> "$SCRIPT_LOG"
echo "==========================================" >> "$SCRIPT_LOG"

python main_daily_ingestion.py >> "$SCRIPT_LOG" 2>&1

EXIT_CODE=$?

echo "==========================================" >> "$SCRIPT_LOG"
echo "Daily Ingestion Finished: $(date) (Exit Code: $EXIT_CODE)" >> "$SCRIPT_LOG"
echo "==========================================" >> "$SCRIPT_LOG"
echo "" >> "$SCRIPT_LOG"

# Exit with the same code as the Python script
exit $EXIT_CODE
SCRIPT_EOF

chmod +x "$CRON_SCRIPT"
print_status "Daily ingestion cron script created: $CRON_SCRIPT"

# Create cron job template
print_status "Creating cron job template..."
CRON_FILE="$PROJECT_DIR/scripts/dreamhost/cron_jobs.txt"
cat > "$CRON_FILE" <<EOF
# RethinkAI Cron Jobs
# Add these to your DreamHost cron jobs (via panel or crontab -e)
# Make sure the script is executable: chmod +x scripts/dreamhost/run_daily_ingestion.sh

# Daily complete ingestion pipeline (runs at 2 AM)
# This runs: Dotnews download, Google Drive sync, Email sync, Boston data sync, and Vector DB build
0 2 * * * $PROJECT_DIR/scripts/dreamhost/run_daily_ingestion.sh

# Alternative: Run individual components separately (if needed)
# Daily Boston data sync only (runs at 2 AM)
# 0 2 * * * cd $PROJECT_DIR/on_the_porch/data_ingestion && $VENV_DIR/bin/python boston_data_sync/boston_data_sync.py >> $LOG_DIR/data_sync.log 2>&1

# Weekly vector database rebuild (runs Sunday at 4 AM) - Optional, usually handled by daily ingestion
# 0 4 * * 0 cd $PROJECT_DIR/on_the_porch/data_ingestion && $VENV_DIR/bin/python build_vectordb.py >> $LOG_DIR/vectordb_build.log 2>&1
EOF

print_status "Cron job template created: $CRON_FILE"

print_status "Deployment complete!"
echo ""
print_warning "Next steps:"
echo "  1. Ensure passenger_wsgi.py and .htaccess are in your web-accessible directory"
echo "  2. Set up cron job for daily ingestion at 2 AM:"
echo "     - Via DreamHost panel: Goodies → Cron Jobs"
echo "     - Command: $PROJECT_DIR/scripts/dreamhost/run_daily_ingestion.sh"
echo "     - Schedule: 0 2 * * *"
echo "     - Or use: crontab -e and add the line from $CRON_FILE"
echo "  3. Test the API endpoint"
echo "  4. Monitor logs in: $LOG_DIR"
echo "     - Daily ingestion: $LOG_DIR/daily_ingestion.log"
echo ""
print_warning "For DreamHost:"
echo "  - Make sure your domain is set up with Passenger"
echo "  - Check that Python version matches your virtual environment"
echo "  - Verify file permissions (644 for files, 755 for directories)"
echo "  - Cron script is executable: chmod +x $CRON_SCRIPT"

