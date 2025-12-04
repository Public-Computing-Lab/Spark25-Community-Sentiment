#!/bin/bash
# Daily Ingestion Cron Job Script
# Runs the complete daily ingestion pipeline at 2 AM
# This script should be called from cron

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

