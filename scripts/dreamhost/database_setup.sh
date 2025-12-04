#!/bin/bash
# DreamHost Database Setup Script
# This script initializes the MySQL database for RethinkAI

set -e  # Exit on error

echo "=========================================="
echo "RethinkAI Database Setup"
echo "=========================================="

# Configuration
PROJECT_DIR="$HOME/ml-misi-community-sentiment"
VENV_DIR="$PROJECT_DIR/venv"

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

# Check if .env file exists
if [ ! -f "$PROJECT_DIR/api/.env" ]; then
    print_error "api/.env file not found. Please create it first."
    exit 1
fi

# Load environment variables
source "$VENV_DIR/bin/activate"

# Extract database credentials from .env
ENV_FILE="$PROJECT_DIR/api/.env"
MYSQL_HOST=$(grep "^MYSQL_HOST=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "127.0.0.1")
MYSQL_PORT=$(grep "^MYSQL_PORT=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "3306")
MYSQL_USER=$(grep "^MYSQL_USER=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "root")
MYSQL_PASSWORD=$(grep "^MYSQL_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "")
MYSQL_DB=$(grep "^MYSQL_DB=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "rethink_ai_boston")

print_status "Database Configuration:"
echo "  Host: $MYSQL_HOST"
echo "  Port: $MYSQL_PORT"
echo "  User: $MYSQL_USER"
echo "  Database: $MYSQL_DB"
echo ""

# Test database connection
print_status "Testing database connection..."
if [ -z "$MYSQL_PASSWORD" ]; then
    MYSQL_CMD="mysql -h$MYSQL_HOST -P$MYSQL_PORT -u$MYSQL_USER"
else
    MYSQL_CMD="mysql -h$MYSQL_HOST -P$MYSQL_PORT -u$MYSQL_USER -p$MYSQL_PASSWORD"
fi

if ! $MYSQL_CMD -e "SELECT 1;" &>/dev/null; then
    print_error "Cannot connect to MySQL. Please check your credentials in api/.env"
    exit 1
fi

print_status "Database connection successful!"

# Create database if it doesn't exist
print_status "Creating database if it doesn't exist..."
$MYSQL_CMD -e "CREATE DATABASE IF NOT EXISTS \`$MYSQL_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" || {
    print_error "Failed to create database"
    exit 1
}

# Run database initialization scripts
print_status "Initializing database schema..."

# Check if data ingestion setup script exists
if [ -f "$PROJECT_DIR/on_the_porch/data_ingestion/mysql_setup.py" ]; then
    print_status "Running MySQL setup script..."
    cd "$PROJECT_DIR/on_the_porch/data_ingestion"
    python mysql_setup.py || print_warning "MySQL setup script had issues (may be expected if tables already exist)"
fi

# Create interaction_log table (for API v2)
print_status "Creating interaction_log table..."
$MYSQL_CMD "$MYSQL_DB" <<EOF
CREATE TABLE IF NOT EXISTS interaction_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(255),
    app_version VARCHAR(50),
    data_selected TEXT,
    data_attributes TEXT,
    prompt_preamble TEXT,
    client_query TEXT,
    app_response TEXT,
    client_response_rating VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_id (session_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
EOF

print_status "Database setup complete!"
echo ""
print_warning "Next steps:"
echo "  1. Run data sync to populate initial data:"
echo "     cd $PROJECT_DIR/on_the_porch/data_ingestion"
echo "     python boston_data_sync/boston_data_sync.py"
echo "  2. Build vector database for documents:"
echo "     cd $PROJECT_DIR/on_the_porch/data_ingestion"
echo "     python build_vectordb.py"

