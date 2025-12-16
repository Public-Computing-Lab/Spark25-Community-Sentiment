#!/bin/bash
# DreamHost Setup Script
# This script sets up the RethinkAI application on DreamHost
# Run this script on your DreamHost server after initial deployment

set -e  # Exit on error

echo "=========================================="
echo "RethinkAI DreamHost Setup"
echo "=========================================="

# Configuration
PROJECT_DIR="$HOME/ml-misi-community-sentiment"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON_VERSION="3.11"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Check if running on DreamHost
if [ ! -d "$HOME" ]; then
    print_error "Cannot find home directory. Are you on DreamHost?"
    exit 1
fi

print_status "Setting up RethinkAI on DreamHost..."

# Step 1: Create project directory if it doesn't exist
if [ ! -d "$PROJECT_DIR" ]; then
    print_status "Creating project directory: $PROJECT_DIR"
    mkdir -p "$PROJECT_DIR"
else
    print_warning "Project directory already exists: $PROJECT_DIR"
fi

# Step 2: Check Python version
print_status "Checking Python version..."
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3 &> /dev/null; then
    PYTHON_VERSION_CHECK=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [ "$PYTHON_VERSION_CHECK" != "3.11" ]; then
        print_warning "Python 3.11 not found. Using available Python version."
    fi
    PYTHON_CMD="python3"
else
    print_error "Python 3 not found. Please install Python 3.11+"
    exit 1
fi

print_status "Using Python: $($PYTHON_CMD --version)"

# Step 3: Create virtual environment
if [ ! -d "$VENV_DIR" ]; then
    print_status "Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    print_status "Virtual environment created"
else
    print_warning "Virtual environment already exists"
fi

# Step 4: Activate virtual environment and upgrade pip
print_status "Activating virtual environment and upgrading pip..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel

# Step 5: Install dependencies
print_status "Installing dependencies..."
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    pip install -r "$PROJECT_DIR/requirements.txt"
    print_status "Dependencies installed"
else
    print_error "requirements.txt not found in project root!"
    exit 1
fi

# Step 6: Create necessary directories
print_status "Creating necessary directories..."
mkdir -p "$PROJECT_DIR/api/datastore"
mkdir -p "$PROJECT_DIR/api/prompts"
mkdir -p "$PROJECT_DIR/on_the_porch/vectordb_new"
mkdir -p "$PROJECT_DIR/on_the_porch/data_ingestion/temp_downloads"
mkdir -p "$PROJECT_DIR/logs"

# Step 7: Set up environment files
print_status "Setting up environment files..."
if [ ! -f "$PROJECT_DIR/api/.env" ]; then
    if [ -f "$PROJECT_DIR/api/.env.example" ]; then
        cp "$PROJECT_DIR/api/.env.example" "$PROJECT_DIR/api/.env"
        print_warning "Created api/.env from example. Please edit with your values!"
    else
        print_error "api/.env.example not found. Please create api/.env manually."
    fi
fi

if [ ! -f "$PROJECT_DIR/on_the_porch/.env" ]; then
    if [ -f "$PROJECT_DIR/on_the_porch/.env.example" ]; then
        cp "$PROJECT_DIR/on_the_porch/.env.example" "$PROJECT_DIR/on_the_porch/.env"
        print_warning "Created on_the_porch/.env from example. Please edit with your values!"
    else
        print_error "on_the_porch/.env.example not found. Please create on_the_porch/.env manually."
    fi
fi

if [ ! -f "$PROJECT_DIR/on_the_porch/data_ingestion/.env" ]; then
    if [ -f "$PROJECT_DIR/on_the_porch/data_ingestion/.env.example" ]; then
        cp "$PROJECT_DIR/on_the_porch/data_ingestion/.env.example" "$PROJECT_DIR/on_the_porch/data_ingestion/.env"
        print_warning "Created data_ingestion/.env from example. Please edit with your values!"
    else
        print_error "data_ingestion/.env.example not found. Please create data_ingestion/.env manually."
    fi
fi

# Step 8: Set permissions
print_status "Setting file permissions..."
chmod +x "$PROJECT_DIR/api/api_v2.py" 2>/dev/null || true
chmod 755 "$PROJECT_DIR" 2>/dev/null || true

# Step 9: Create log directory with proper permissions
print_status "Setting up logging..."
touch "$PROJECT_DIR/logs/api.log"
chmod 644 "$PROJECT_DIR/logs/api.log"

print_status "Setup complete!"
echo ""
print_warning "IMPORTANT: Next steps:"
echo "  1. Edit environment files (.env) with your API keys and database credentials"
echo "  2. Run database_setup.sh to initialize the database"
echo "  3. Test the API with: python api/api_v2.py"
echo "  4. Set up a WSGI server (gunicorn) for production"
echo "  5. Configure cron jobs for data ingestion (see deploy.sh)"

