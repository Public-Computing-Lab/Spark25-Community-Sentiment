"""
Test script to verify Gmail OAuth and Google Drive API connections.
Lists recent emails and files from Google Drive.
"""
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import config
from email_to_calendar_sql import get_gmail_service, get_gmail_credentials
from google_drive_to_vectordb import get_drive_service
import base64
import email


def test_gmail_connection():
    """Test Gmail OAuth connection and list recent emails."""
    print("\n" + "=" * 80)
    print("TESTING GMAIL CONNECTION")
    print("=" * 80)
    
    try:
        # Test OAuth credentials
        print("\n1. Testing OAuth 2.0 authentication...")
        creds = get_gmail_credentials()
        print(f"   ✓ OAuth credentials valid")
        print(f"   ✓ Token expires: {creds.expiry if creds.expiry else 'No expiry'}")
        
        # Connect to Gmail API
        print("\n2. Connecting to Gmail API...")
        service = get_gmail_service()
        print(f"   ✓ Connected to Gmail API")
        
        # Get profile info
        print("\n3. Getting mailbox info...")
        profile = service.users().getProfile(userId='me').execute()
        email_addr = profile.get('emailAddress', 'Unknown')
        total_messages = profile.get('messagesTotal', 0)
        print(f"   ✓ Account: {email_addr}")
        print(f"   ✓ Total messages: {total_messages}")
        
        # Get 2 most recent emails
        print("\n4. Fetching 2 most recent emails...")
        results = service.users().messages().list(
            userId='me',
            maxResults=2
        ).execute()
        
        messages = results.get('messages', [])
        
        if messages:
            print(f"\n   Found {len(messages)} recent email(s):\n")
            
            for i, msg_ref in enumerate(messages, 1):
                try:
                    message = service.users().messages().get(
                        userId='me',
                        id=msg_ref['id'],
                        format='raw'
                    ).execute()
                    
                    # Decode the raw message
                    raw_email = base64.urlsafe_b64decode(message['raw'])
                    msg = email.message_from_bytes(raw_email)
                    
                    subject = msg.get('Subject', 'No Subject')
                    sender = msg.get('From', 'Unknown')
                    date = msg.get('Date', 'Unknown')
                    
                    print(f"   Email #{i}:")
                    print(f"   - Subject: {subject[:70]}...")
                    print(f"   - From: {sender}")
                    print(f"   - Date: {date}")
                    print()
                except Exception as e:
                    print(f"   ✗ Error reading email: {e}")
        else:
            print("\n   ⚠ No emails found in inbox")
        
        print("✓ Gmail connection test successful!\n")
        return True
        
    except FileNotFoundError as e:
        print(f"\n✗ OAuth credentials file not found: {e}")
        print(f"   Please download gmail_credentials.json from Google Cloud Console")
        print(f"   and place it at: {config.GMAIL_CREDENTIALS_PATH}\n")
        return False
        
    except Exception as e:
        print(f"\n✗ Gmail connection failed: {e}\n")
        return False


def test_google_drive_connection():
    """Test Google Drive API connection and list files."""
    print("=" * 80)
    print("TESTING GOOGLE DRIVE CONNECTION")
    print("=" * 80)
    
    try:
        # Test service account credentials
        print("\n1. Testing service account authentication...")
        service = get_drive_service()
        print(f"   ✓ Service account authenticated")
        print(f"   ✓ Using credentials: {config.GOOGLE_CREDENTIALS_PATH}")
        
        # List files in the folder
        print(f"\n2. Listing files in folder: {config.GOOGLE_DRIVE_FOLDER_ID}...")
        
        query = f"'{config.GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed=false"
        results = service.files().list(
            q=query,
            fields="files(id, name, mimeType, modifiedTime, size)",
            pageSize=20,
            orderBy="modifiedTime desc"
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            print("\n   ⚠ No files found in the folder")
            print("   Make sure the folder ID is correct and files are uploaded")
        else:
            print(f"\n   Found {len(files)} file(s):\n")
            
            for i, file in enumerate(files, 1):
                name = file.get('name', 'Unknown')
                modified = file.get('modifiedTime', 'Unknown')
                size = file.get('size', 'N/A')
                mime = file.get('mimeType', 'Unknown')
                
                # Convert size to human readable
                if size != 'N/A':
                    try:
                        size_bytes = int(size)
                        if size_bytes < 1024:
                            size_str = f"{size_bytes} B"
                        elif size_bytes < 1024 * 1024:
                            size_str = f"{size_bytes / 1024:.1f} KB"
                        else:
                            size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                    except:
                        size_str = size
                else:
                    size_str = "Folder"
                
                # Get file extension
                ext = Path(name).suffix.lower()
                supported = "✓" if ext in config.SUPPORTED_EXTENSIONS else "✗"
                
                print(f"   File #{i}:")
                print(f"   - Name: {name}")
                print(f"   - Size: {size_str}")
                print(f"   - Modified: {modified}")
                print(f"   - Supported for ingestion: {supported}")
                print()
        
        print("✓ Google Drive connection test successful!\n")
        return True
        
    except FileNotFoundError as e:
        print(f"\n✗ Service account credentials not found: {e}")
        print(f"   Please download credentials JSON from Google Cloud Console")
        print(f"   and place it at: {config.GOOGLE_CREDENTIALS_PATH}\n")
        return False
        
    except Exception as e:
        print(f"\n✗ Google Drive connection failed: {e}")
        print(f"   Check that:")
        print(f"   1. GOOGLE_DRIVE_FOLDER_ID is correct in .env")
        print(f"   2. Service account has access to the folder")
        print(f"   3. Google Drive API is enabled\n")
        return False


def main():
    """Run all connection tests."""
    print("\n╔" + "=" * 78 + "╗")
    print("║" + " " * 25 + "CONNECTION TEST SCRIPT" + " " * 31 + "║")
    print("║" + " " * 20 + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " * 30 + "║")
    print("╚" + "=" * 78 + "╝\n")
    
    # Validate configuration
    print("Checking configuration...")
    errors = config.validate_config()
    if errors:
        print("\n⚠ Configuration errors found:")
        for error in errors:
            print(f"   - {error}")
        print("\nPlease fix these errors in your .env file before running tests.\n")
        return
    
    print("✓ Configuration valid\n")
    
    # Run tests
    gmail_ok = test_gmail_connection()
    drive_ok = test_google_drive_connection()
    
    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Gmail Connection:        {'✓ PASS' if gmail_ok else '✗ FAIL'}")
    print(f"Google Drive Connection: {'✓ PASS' if drive_ok else '✗ FAIL'}")
    print("=" * 80)
    
    if gmail_ok and drive_ok:
        print("\n✅ All tests passed! You're ready to run the ingestion scripts.\n")
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above before running ingestion.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.\n")
    except Exception as e:
        print(f"\n\nFatal error: {e}\n")
        import traceback
        traceback.print_exc()

