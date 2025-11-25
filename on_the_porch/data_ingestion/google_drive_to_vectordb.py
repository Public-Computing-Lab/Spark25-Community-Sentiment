"""
Google Drive to Vector DB Ingestion
Downloads new files from a shared Google Drive folder and adds them to the vector database.
"""
import json
import sys
from pathlib import Path
from typing import List, Dict
from datetime import datetime

# Google Drive API
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# Document processing
from langchain_community.vectorstores import Chroma

# Local imports
sys.path.insert(0, str(Path(__file__).parent.parent / "rag stuff"))
from retrieval import GeminiEmbeddings

import config
from utils.document_processor import process_file_to_documents


def load_sync_state() -> dict:
    """Load the state of what files have been synced."""
    if config.SYNC_STATE_FILE.exists():
        try:
            return json.loads(config.SYNC_STATE_FILE.read_text())
        except Exception:
            return {"processed_files": {}, "last_sync": None}
    return {"processed_files": {}, "last_sync": None}


def save_sync_state(state: dict) -> None:
    """Save the sync state to track processed files."""
    state["last_sync"] = datetime.now().isoformat()
    config.SYNC_STATE_FILE.write_text(json.dumps(state, indent=2))


def get_drive_service():
    """Authenticate and return Google Drive service."""
    if not Path(config.GOOGLE_CREDENTIALS_PATH).exists():
        raise FileNotFoundError(
            f"Google credentials file not found: {config.GOOGLE_CREDENTIALS_PATH}"
        )
    
    creds = ServiceAccountCredentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_PATH,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)


def list_new_files_from_drive(service, folder_id: str, processed_files: dict) -> List[dict]:
    """
    List all files in the Google Drive folder that haven't been processed yet.
    Returns list of file metadata: {id, name, mimeType, modifiedTime}
    """
    if not folder_id:
        raise ValueError("GOOGLE_DRIVE_FOLDER_ID is not set")
    
    query = f"'{folder_id}' in parents and trashed=false"
    
    try:
        results = service.files().list(
            q=query,
            fields="files(id, name, mimeType, modifiedTime, md5Checksum)",
            pageSize=1000
        ).execute()
    except Exception as e:
        raise RuntimeError(f"Failed to list files from Google Drive: {e}")
    
    all_files = results.get('files', [])
    
    # Filter out already processed files (check by ID and modified time)
    new_files = []
    for file in all_files:
        file_id = file['id']
        modified_time = file.get('modifiedTime', '')
        
        # Check if we've seen this file with the same modification time
        if file_id in processed_files:
            if processed_files[file_id].get('modifiedTime') == modified_time:
                continue  # Already processed this version
        
        # Check file extension
        ext = Path(file['name']).suffix.lower()
        if ext in config.SUPPORTED_EXTENSIONS:
            new_files.append(file)
    
    return new_files


def download_file(service, file_id: str, file_name: str) -> Path:
    """Download a file from Google Drive to temp directory."""
    request = service.files().get_media(fileId=file_id)
    local_path = config.TEMP_DOWNLOAD_DIR / file_name
    
    try:
        with io.FileIO(local_path, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status and config.VERBOSE_LOGGING:
                    print(f"    Download {int(status.progress() * 100)}%")
    except Exception as e:
        raise RuntimeError(f"Failed to download file {file_name}: {e}")
    
    return local_path


def add_documents_to_vectordb(documents: List) -> None:
    """Add new documents to the existing vector database."""
    if not documents:
        print("No documents to add.")
        return
    
    embeddings = GeminiEmbeddings()
    
    # Load existing vector DB or create new one
    if config.VECTORDB_DIR.exists():
        vectordb = Chroma(
            persist_directory=str(config.VECTORDB_DIR),
            embedding_function=embeddings
        )
        # Add new documents
        vectordb.add_documents(documents)
        print(f"✓ Added {len(documents)} new document chunks to existing vector DB.")
    else:
        # Create new vector DB
        vectordb = Chroma.from_documents(
            documents=documents,
            embedding=embeddings,
            persist_directory=str(config.VECTORDB_DIR)
        )
        print(f"✓ Created new vector DB with {len(documents)} document chunks.")


def cleanup_temp_files() -> None:
    """Clean up temporary downloaded files."""
    for file in config.TEMP_DOWNLOAD_DIR.glob("*"):
        if file.is_file():
            try:
                file.unlink()
            except Exception:
                pass


def sync_google_drive_to_vectordb() -> dict:
    """
    Main function to sync Google Drive files to vector database.
    Returns summary statistics.
    """
    print("=" * 80)
    print("Starting Google Drive → Vector DB Sync")
    print("=" * 80)
    
    stats = {
        'files_processed': 0,
        'chunks_added': 0,
        'errors': []
    }
    
    try:
        # Validate configuration
        errors = config.validate_config()
        drive_errors = [e for e in errors if 'GOOGLE_DRIVE' in e or 'Google credentials' in e]
        if drive_errors:
            for error in drive_errors:
                print(f"✗ Configuration error: {error}")
                stats['errors'].append(error)
            return stats
        
        # Load sync state
        state = load_sync_state()
        processed_files = state.get('processed_files', {})
        
        # Get Drive service
        print("Authenticating with Google Drive...")
        service = get_drive_service()
        print("✓ Authenticated successfully")
        
        # List new files
        print(f"Scanning folder {config.GOOGLE_DRIVE_FOLDER_ID}...")
        new_files = list_new_files_from_drive(
            service, 
            config.GOOGLE_DRIVE_FOLDER_ID, 
            processed_files
        )
        
        print(f"Found {len(new_files)} new or updated files to process.")
        
        if not new_files:
            print("No new files to process. Exiting.")
            return stats
        
        all_documents = []
        
        # Process each new file
        for i, file_meta in enumerate(new_files[:config.MAX_FILES_PER_RUN], 1):
            try:
                print(f"\n[{i}/{len(new_files)}] Processing: {file_meta['name']}")
                
                # Download file
                local_path = download_file(service, file_meta['id'], file_meta['name'])
                print(f"  ✓ Downloaded to {local_path.name}")
                
                # Extract text and create documents
                documents = process_file_to_documents(local_path, file_meta)
                all_documents.extend(documents)
                
                # Mark as processed
                processed_files[file_meta['id']] = {
                    'name': file_meta['name'],
                    'modifiedTime': file_meta.get('modifiedTime', ''),
                    'processed_at': datetime.now().isoformat(),
                    'chunks': len(documents)
                }
                
                stats['files_processed'] += 1
                print(f"  ✓ Extracted {len(documents)} chunks")
                
            except Exception as e:
                error_msg = f"Error processing {file_meta['name']}: {str(e)}"
                print(f"  ✗ {error_msg}")
                stats['errors'].append(error_msg)
        
        # Add all documents to vector DB in one batch
        if all_documents:
            print(f"\nAdding {len(all_documents)} chunks to vector database...")
            add_documents_to_vectordb(all_documents)
            stats['chunks_added'] = len(all_documents)
        
        # Save updated sync state
        state['processed_files'] = processed_files
        save_sync_state(state)
        print("✓ Sync state saved")
        
        # Cleanup
        cleanup_temp_files()
        print("✓ Temporary files cleaned up")
        
    except Exception as e:
        error_msg = f"Fatal error during sync: {str(e)}"
        print(f"\n✗ {error_msg}")
        stats['errors'].append(error_msg)
    
    print("\n" + "=" * 80)
    print("Google Drive Sync Complete")
    print(f"Files processed: {stats['files_processed']}")
    print(f"Chunks added: {stats['chunks_added']}")
    print(f"Errors: {len(stats['errors'])}")
    print("=" * 80)
    
    return stats


if __name__ == "__main__":
    try:
        sync_google_drive_to_vectordb()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        sys.exit(1)

