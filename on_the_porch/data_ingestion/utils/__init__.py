"""
Utility modules for data ingestion.
"""
from .document_processor import extract_text_from_file, process_file_to_documents
from .email_parser import extract_text_from_email, extract_pdf_attachments, clean_html

__all__ = [
    'extract_text_from_file',
    'process_file_to_documents',
    'extract_text_from_email',
    'extract_pdf_attachments',
    'clean_html',
]

