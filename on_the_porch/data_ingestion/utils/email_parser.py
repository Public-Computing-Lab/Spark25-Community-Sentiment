"""
Email parsing utilities for extracting content from email messages.
"""
import email
from email.header import decode_header
from typing import List
import re
import io

from pypdf import PdfReader
from bs4 import BeautifulSoup


def decode_email_header(header_value):
    """Decode email header that may be encoded."""
    if not header_value:
        return ""
    
    decoded_parts = decode_header(header_value)
    result = []
    
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            if encoding:
                try:
                    result.append(part.decode(encoding))
                except Exception:
                    result.append(part.decode('utf-8', errors='ignore'))
            else:
                result.append(part.decode('utf-8', errors='ignore'))
        else:
            result.append(str(part))
    
    return ''.join(result)


def clean_html(html_content: str) -> str:
    """
    Clean HTML content and extract plain text.
    
    Args:
        html_content: HTML string
        
    Returns:
        Plain text with HTML tags removed
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Remove script and style elements
        for script in soup(['script', 'style']):
            script.decompose()
        
        # Get text
        text = soup.get_text()
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
    except Exception:
        # Fallback: simple regex-based HTML removal
        text = re.sub('<[^<]+?>', '', html_content)
        return text.strip()


def extract_text_from_email(msg) -> str:
    """
    Extract text content from an email message.
    
    Args:
        msg: email.message.Message object
        
    Returns:
        Extracted text content from email body
    """
    text_content = []
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            # Skip attachments
            if "attachment" in content_disposition:
                continue
            
            try:
                if content_type == "text/plain":
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    text_content.append(body)
                    
                elif content_type == "text/html":
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    clean_text = clean_html(body)
                    text_content.append(clean_text)
            except Exception:
                # Skip parts that fail to decode
                continue
    else:
        # Not multipart - single body
        try:
            content_type = msg.get_content_type()
            body = msg.get_payload(decode=True)
            
            if body:
                body_text = body.decode('utf-8', errors='ignore')
                if content_type == "text/html":
                    body_text = clean_html(body_text)
                text_content.append(body_text)
        except Exception:
            pass
    
    return "\n\n".join(text_content)


def extract_pdf_attachments(msg) -> List[str]:
    """
    Extract text from PDF attachments in an email.
    
    Args:
        msg: email.message.Message object
        
    Returns:
        List of extracted text strings from PDF attachments
    """
    pdf_texts = []
    
    if not msg.is_multipart():
        return pdf_texts
    
    for part in msg.walk():
        content_type = part.get_content_type()
        content_disposition = str(part.get("Content-Disposition", ""))
        
        # Check if this is a PDF attachment
        if content_type == "application/pdf" or (
            "attachment" in content_disposition and 
            part.get_filename() and 
            part.get_filename().lower().endswith('.pdf')
        ):
            try:
                pdf_data = part.get_payload(decode=True)
                pdf_file = io.BytesIO(pdf_data)
                reader = PdfReader(pdf_file)
                
                text = "\n\n".join(
                    page.extract_text() or "" for page in reader.pages
                )
                
                if text.strip():
                    pdf_texts.append(text.strip())
                    
            except Exception as e:
                # Log warning but continue processing
                print(f"  Warning: Could not extract PDF attachment: {e}")
                continue
    
    return pdf_texts


def get_email_subject(msg) -> str:
    """
    Get the subject line from an email message.
    
    Args:
        msg: email.message.Message object
        
    Returns:
        Decoded subject string
    """
    subject = msg.get("Subject", "")
    return decode_email_header(subject)


def get_email_sender(msg) -> str:
    """
    Get the sender (From) from an email message.
    
    Args:
        msg: email.message.Message object
        
    Returns:
        Decoded sender string
    """
    sender = msg.get("From", "")
    return decode_email_header(sender)


def get_email_date(msg) -> str:
    """
    Get the date from an email message.
    
    Args:
        msg: email.message.Message object
        
    Returns:
        Date string
    """
    return msg.get("Date", "")


def extract_all_attachments_info(msg) -> List[dict]:
    """
    Get information about all attachments in an email.
    
    Args:
        msg: email.message.Message object
        
    Returns:
        List of dicts with attachment info (filename, content_type, size)
    """
    attachments = []
    
    if not msg.is_multipart():
        return attachments
    
    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", ""))
        
        if "attachment" in content_disposition:
            filename = part.get_filename()
            if filename:
                filename = decode_email_header(filename)
                
                # Get size if available
                payload = part.get_payload(decode=True)
                size = len(payload) if payload else 0
                
                attachments.append({
                    'filename': filename,
                    'content_type': part.get_content_type(),
                    'size': size
                })
    
    return attachments

