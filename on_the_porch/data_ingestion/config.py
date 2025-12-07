"""
Configuration module for automated data ingestion.
Loads all settings from environment variables (.env file).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the repo root .env
_THIS_DIR = Path(__file__).parent
_ROOT_DIR = _THIS_DIR.parents[2]
_ENV_FILE = _ROOT_DIR / ".env"

if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)

# ============================================================================
# Google Drive Configuration
# ============================================================================
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "service_account_credentials.json")

# Convert to absolute path if relative
if GOOGLE_CREDENTIALS_PATH and not Path(GOOGLE_CREDENTIALS_PATH).is_absolute():
    GOOGLE_CREDENTIALS_PATH = str(_THIS_DIR / GOOGLE_CREDENTIALS_PATH)

# ============================================================================
# Email Configuration (Gmail OAuth 2.0)
# ============================================================================
EMAIL_ADDRESS = os.getenv("NEWSLETTER_EMAIL_ADDRESS", "")

# OAuth 2.0 credentials (for Gmail)
GMAIL_CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH", "gmail_credentials.json")
GMAIL_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH", "gmail_token.json")

# Convert to absolute path if relative
if GMAIL_CREDENTIALS_PATH and not Path(GMAIL_CREDENTIALS_PATH).is_absolute():
    GMAIL_CREDENTIALS_PATH = str(_THIS_DIR / GMAIL_CREDENTIALS_PATH)
if GMAIL_TOKEN_PATH and not Path(GMAIL_TOKEN_PATH).is_absolute():
    GMAIL_TOKEN_PATH = str(_THIS_DIR / GMAIL_TOKEN_PATH)

# IMAP settings (Gmail defaults)
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))

# ============================================================================
# File Paths Configuration
# ============================================================================
# Vector DB directory (main documents)
_VECTORDB_DIR_RAW = os.getenv("VECTORDB_DIR", "../vectordb_new")
if Path(_VECTORDB_DIR_RAW).is_absolute():
    VECTORDB_DIR = Path(_VECTORDB_DIR_RAW)
else:
    VECTORDB_DIR = (_THIS_DIR / _VECTORDB_DIR_RAW).resolve()

# NOTE: Calendar events are now SQL-only (weekly_events table), no vector DB needed.

# Temporary download directory
_TEMP_DIR_RAW = os.getenv("TEMP_DOWNLOAD_DIR", "./temp_downloads")
if Path(_TEMP_DIR_RAW).is_absolute():
    TEMP_DOWNLOAD_DIR = Path(_TEMP_DIR_RAW)
else:
    TEMP_DOWNLOAD_DIR = (_THIS_DIR / _TEMP_DIR_RAW).resolve()

# Ensure temp directory exists
TEMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Database Configuration
# ============================================================================
DATABASE_URL = os.getenv("DATABASE_URL", "")
PGSCHEMA = os.getenv("PGSCHEMA", "public")

# ============================================================================
# Gemini AI Configuration
# ============================================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
GEMINI_SUMMARY_MODEL = os.getenv("GEMINI_SUMMARY_MODEL", GEMINI_MODEL)

# ============================================================================
# Processing Configuration
# ============================================================================
EMAIL_LOOKBACK_DAYS = int(os.getenv("EMAIL_LOOKBACK_DAYS", "7"))
MAX_FILES_PER_RUN = int(os.getenv("MAX_FILES_PER_RUN", "100"))
VERBOSE_LOGGING = os.getenv("VERBOSE_LOGGING", "false").lower() in ("true", "1", "yes")

# ============================================================================
# Sync State Files
# ============================================================================
SYNC_STATE_FILE = _THIS_DIR / ".sync_state.json"
EMAIL_SYNC_STATE_FILE = _THIS_DIR / ".email_sync_state.json"

# ============================================================================
# Supported File Extensions for Vector DB
# ============================================================================
SUPPORTED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.txt', '.md'}


# ============================================================================
# Validation
# ============================================================================
def validate_config() -> list:
    """
    Validate that required configuration is present.
    Returns a list of error messages (empty if all valid).
    """
    errors = []
    
    # Check Google Drive config
    if not GOOGLE_DRIVE_FOLDER_ID:
        errors.append("GOOGLE_DRIVE_FOLDER_ID is not set")
    
    if not Path(GOOGLE_CREDENTIALS_PATH).exists():
        errors.append(f"Google credentials file not found: {GOOGLE_CREDENTIALS_PATH}")
    
    # Check Email config (Gmail OAuth)
    if not EMAIL_ADDRESS:
        errors.append("NEWSLETTER_EMAIL_ADDRESS is not set")
    
    if not Path(GMAIL_CREDENTIALS_PATH).exists():
        errors.append(f"Gmail OAuth credentials file not found: {GMAIL_CREDENTIALS_PATH}")
    
    # Check Gemini config
    if not GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY is not set")
    
    # Check Database config
    if not DATABASE_URL:
        errors.append("DATABASE_URL is not set")
    
    return errors


def print_config_summary():
    """Print a summary of the current configuration (hiding sensitive data)."""
    print("=" * 80)
    print("Configuration Summary")
    print("=" * 80)
    print(f"Google Drive Folder ID: {GOOGLE_DRIVE_FOLDER_ID[:20]}..." if len(GOOGLE_DRIVE_FOLDER_ID) > 20 else f"Google Drive Folder ID: {GOOGLE_DRIVE_FOLDER_ID}")
    print(f"Google Credentials: {GOOGLE_CREDENTIALS_PATH}")
    print(f"Email Address: {EMAIL_ADDRESS}")
    print(f"Gmail OAuth Credentials: {GMAIL_CREDENTIALS_PATH}")
    print(f"Gmail Token File: {GMAIL_TOKEN_PATH}")
    print(f"IMAP Server: {IMAP_SERVER}:{IMAP_PORT}")
    print(f"Vector DB Directory: {VECTORDB_DIR}")
    print(f"Temp Download Directory: {TEMP_DOWNLOAD_DIR}")
    print(f"Database: {'Configured' if DATABASE_URL else 'Not configured'}")
    print(f"Gemini Model: {GEMINI_MODEL}")
    print(f"Email Lookback Days: {EMAIL_LOOKBACK_DAYS}")
    print(f"Max Files Per Run: {MAX_FILES_PER_RUN}")
    print(f"Verbose Logging: {VERBOSE_LOGGING}")
    print("=" * 80)
    
    # Check for errors
    errors = validate_config()
    if errors:
        print("\n⚠️  Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
        print()


if __name__ == "__main__":
    # When run directly, print configuration summary
    print_config_summary()

