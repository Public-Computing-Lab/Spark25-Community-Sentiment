"""
Download the latest PDF from Dorchester Reporter's inprint page.

This script fetches the latest PDF issue from https://www.dotnews.com/inprint/
without using Selenium - just requests and BeautifulSoup.
"""
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin, urlparse
import re
from typing import Optional


def download_latest_pdf(
    base_url: str = "https://www.dotnews.com/inprint/",
    output_dir: Optional[Path] = None
) -> Optional[Path]:
    """
    Download the latest PDF from the Dorchester Reporter inprint page.
    
    Args:
        base_url: The URL of the inprint page
        output_dir: Directory to save the PDF. If None, saves to current directory.
        
    Returns:
        Path to the downloaded PDF file, or None if download failed
    """
    # Set up output directory
    if output_dir is None:
        output_dir = Path.cwd()
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Fetch the HTML page
    print(f"Fetching {base_url}...")
    try:
        response = requests.get(base_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching page: {e}")
        return None
    
    # Parse HTML
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find all "Read Issue" links - they appear in the News Archives section
    # Looking for links that contain "Read Issue" or similar text
    read_issue_links = []
    
    # Try multiple strategies to find the PDF links
    # Strategy 1: Look for links with "Read Issue" text
    for link in soup.find_all('a', href=True):
        link_text = link.get_text(strip=True).lower()
        if 'read issue' in link_text or 'read more' in link_text:
            href = link.get('href')
            if href:
                full_url = urljoin(base_url, href)
                read_issue_links.append((link_text, full_url))
    
    # Strategy 2: Look for links in the News Archives section
    # The archives are organized by month, and the first entry should be the latest
    if not read_issue_links:
        # Look for archive sections
        archive_sections = soup.find_all(['div', 'section', 'article'], class_=re.compile(r'archive|news|issue', re.I))
        for section in archive_sections:
            links = section.find_all('a', href=True)
            for link in links:
                href = link.get('href')
                if href and ('.pdf' in href.lower() or 'issue' in href.lower() or 'read' in link.get_text(strip=True).lower()):
                    full_url = urljoin(base_url, href)
                    read_issue_links.append((link.get_text(strip=True), full_url))
    
    # Strategy 3: Look for any PDF links directly
    if not read_issue_links:
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if href and '.pdf' in href.lower():
                full_url = urljoin(base_url, href)
                read_issue_links.append((link.get_text(strip=True), full_url))
    
    if not read_issue_links:
        print("Could not find any PDF links on the page.")
        print("Page structure might have changed. Here's a sample of the HTML:")
        print(soup.prettify()[:1000])
        return None
    
    # The first link should be the latest issue
    latest_link_text, latest_url = read_issue_links[0]
    print(f"Found latest issue: {latest_link_text}")
    print(f"PDF URL: {latest_url}")
    
    # Download the PDF
    print("Downloading PDF...")
    try:
        pdf_response = requests.get(latest_url, timeout=60, stream=True)
        pdf_response.raise_for_status()
        
        # Determine filename
        # Try to get filename from Content-Disposition header
        content_disposition = pdf_response.headers.get('Content-Disposition', '')
        if 'filename=' in content_disposition:
            filename = re.findall(r'filename="?([^"]+)"?', content_disposition)[0]
        else:
            # Extract from URL
            parsed_url = urlparse(latest_url)
            filename = Path(parsed_url.path).name
            if not filename or not filename.endswith('.pdf'):
                # Generate a filename based on the link text
                filename = f"dorchester_reporter_{latest_link_text.replace(' ', '_').replace('/', '_')}.pdf"
                if not filename.endswith('.pdf'):
                    filename += '.pdf'
        
        # Clean filename
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        # Save the PDF
        output_path = output_dir / filename
        with open(output_path, 'wb') as f:
            for chunk in pdf_response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"✓ Successfully downloaded: {output_path}")
        print(f"  File size: {output_path.stat().st_size / 1024:.2f} KB")
        return output_path
        
    except requests.RequestException as e:
        print(f"Error downloading PDF: {e}")
        return None


if __name__ == "__main__":
    # Optionally use a downloads directory
    downloads_dir = Path(__file__).parent.parent / "temp_downloads" / "dotnews"
    result = download_latest_pdf(output_dir=downloads_dir)
    if result:
        print(f"\nPDF saved to: {result.absolute()}")
    else:
        print("\nDownload failed.")

