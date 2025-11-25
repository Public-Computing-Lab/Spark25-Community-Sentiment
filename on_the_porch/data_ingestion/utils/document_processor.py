"""
Document processing utilities for extracting text from various file formats.
"""
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from pypdf import PdfReader
import docx
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


def extract_text_from_pdf(file_path: Path) -> str:
    """Extract text from a PDF file."""
    try:
        reader = PdfReader(file_path)
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        return text.strip()
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {e}")


def extract_text_from_docx(file_path: Path) -> str:
    """Extract text from a DOCX file."""
    try:
        doc = docx.Document(file_path)
        paragraphs = [paragraph.text for paragraph in doc.paragraphs]
        return "\n\n".join(paragraphs).strip()
    except Exception as e:
        raise ValueError(f"Failed to extract text from DOCX: {e}")


def extract_text_from_txt(file_path: Path) -> str:
    """Extract text from a plain text file."""
    try:
        return file_path.read_text(encoding='utf-8', errors='ignore').strip()
    except Exception as e:
        raise ValueError(f"Failed to read text file: {e}")


def extract_text_from_file(file_path: Path) -> str:
    """
    Extract text from various file formats.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Extracted text content
        
    Raises:
        ValueError: If file format is unsupported or extraction fails
    """
    ext = file_path.suffix.lower()
    
    if ext == '.pdf':
        return extract_text_from_pdf(file_path)
    elif ext == '.docx':
        return extract_text_from_docx(file_path)
    elif ext == '.doc':
        # For old .doc files, try DOCX library (may not work for all)
        return extract_text_from_docx(file_path)
    elif ext in {'.txt', '.md'}:
        return extract_text_from_txt(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def process_file_to_documents(
    file_path: Path,
    file_metadata: Dict[str, Any],
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> List[Document]:
    """
    Process a file into LangChain documents for the vector DB.
    
    Args:
        file_path: Path to the file
        file_metadata: Metadata about the file (id, name, modifiedTime, etc.)
        chunk_size: Size of text chunks
        chunk_overlap: Overlap between chunks
        
    Returns:
        List of Document objects ready for vector DB ingestion
    """
    # Extract text from file
    text = extract_text_from_file(file_path)
    
    if not text.strip():
        return []
    
    # Split into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    chunks = text_splitter.split_text(text)
    
    # Create documents with metadata
    documents = []
    for i, chunk in enumerate(chunks):
        doc = Document(
            page_content=chunk,
            metadata={
                'source': file_metadata.get('name', 'unknown'),
                'doc_type': 'client_upload',
                'chunk_id': i,
                'drive_file_id': file_metadata.get('id', ''),
                'modified_time': file_metadata.get('modifiedTime', ''),
                'ingestion_date': datetime.now().isoformat(),
                'file_extension': file_path.suffix.lower()
            }
        )
        documents.append(doc)
    
    return documents


def validate_file(file_path: Path, supported_extensions: set) -> bool:
    """
    Check if a file is valid and supported.
    
    Args:
        file_path: Path to the file
        supported_extensions: Set of supported file extensions (e.g., {'.pdf', '.docx'})
        
    Returns:
        True if file is valid, False otherwise
    """
    if not file_path.exists():
        return False
    
    if not file_path.is_file():
        return False
    
    if file_path.suffix.lower() not in supported_extensions:
        return False
    
    # Check file size (skip very large files > 50MB)
    if file_path.stat().st_size > 50 * 1024 * 1024:
        return False
    
    return True


def get_file_info(file_path: Path) -> Dict[str, Any]:
    """
    Get basic information about a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary with file information
    """
    stat = file_path.stat()
    return {
        'name': file_path.name,
        'size': stat.st_size,
        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
        'extension': file_path.suffix.lower()
    }


def events_to_documents(events: List[Dict[str, Any]], source: str = "unknown") -> List[Document]:
    """
    Convert event dictionaries into LangChain Documents for the calendar vector DB.
    
    This follows the same approach as build_calendar_vectordb.py in the rag stuff folder,
    creating documents optimized for semantic search of calendar events.
    
    Args:
        events: List of event dictionaries with keys:
            - event_name: Short descriptive name
            - event_date: Date label as written (e.g., "Monday", "June 3-5")
            - start_date: ISO date YYYY-MM-DD (or None)
            - end_date: ISO date YYYY-MM-DD (or None)
            - start_time: 24-hour time HH:MM (or None)
            - end_time: 24-hour time HH:MM (or None)
            - raw_text: Original text describing the event
            - location: Where the event takes place (optional)
        source: Source identifier (e.g., "Email: Newsletter Subject")
        
    Returns:
        List of Document objects ready for calendar vector DB ingestion
    """
    documents = []
    
    for event in events:
        raw_text = (event.get("raw_text") or "").strip()
        if not raw_text:
            continue
        
        # Build metadata matching the build_calendar_vectordb.py format
        metadata = {
            "source": source,
            "doc_type": "calendar_event",
            "ingestion_date": datetime.now().isoformat(),
        }
        
        # Add all event fields to metadata (except raw_text which becomes page_content)
        for key, value in event.items():
            if key == "raw_text":
                continue
            if value is not None and value != "":
                metadata[key] = value
        
        documents.append(Document(page_content=raw_text, metadata=metadata))
    
    return documents
