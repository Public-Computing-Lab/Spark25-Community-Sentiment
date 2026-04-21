#!/bin/bash
# Daily Ingestion Cron Job Script
# Runs the complete daily ingestion pipeline at 2 AM
# This script should be called from cron

# Configuration
PROJECT_DIR="$HOME/ml-misi-community-sentiment"
VENV_DIR="$PROJECT_DIR/.venv_demo"
INGESTION_DIR="$PROJECT_DIR/on_the_porch/data_ingestion"
LOG_DIR="$PROJECT_DIR/logs"
SCRIPT_LOG="$LOG_DIR/daily_ingestion.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Fail fast on setup errors (before the Python run)
set -e

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

# Ensure MySQL container is running
if ! docker ps --format '{{.Names}}' | grep -q '^mysql_demo$'; then
    echo "ERROR: mysql_demo container is not running at $(date)" >> "$SCRIPT_LOG"
    exit 1
fi

# Turn off set -e so we can capture the Python exit code ourselves
set +e

# Run the main daily ingestion script
{
    echo "=========================================="
    echo "Daily Ingestion Started: $(date)"
    echo "=========================================="
} >> "$SCRIPT_LOG"

python main_daily_ingestion.py >> "$SCRIPT_LOG" 2>&1
EXIT_CODE=$?

{
    echo "=========================================="
    echo "Daily Ingestion Finished: $(date) (Exit Code: $EXIT_CODE)" 
    echo "=========================================="
    echo ""
} >> "$SCRIPT_LOG"

exit $EXIT_CODE
