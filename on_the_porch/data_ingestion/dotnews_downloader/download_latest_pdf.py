"""
Download the latest PDF from Dorchester Reporter's inprint page.

This script fetches the latest PDF issue from https://www.dotnews.com/inprint/
The website structure:
1. /inprint/ page has links to monthly archives
2. Monthly archive pages have "Download issue" links to individual issue pages
3. Individual issue pages have the PDF embedded in an <embed> tag

This script follows this structure to find and download the latest PDF.
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
    
    The new website structure requires:
    1. Go to /inprint/ page
    2. Find the latest monthly archive link
    3. Go to that monthly archive page
    4. Find the latest "Download issue" link
    5. Go to that issue page
    6. Find the PDF in an <embed> tag
    7. Download the PDF
    
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
    
    # Step 1: Fetch the inprint page to find monthly archive links
    print(f"Step 1: Fetching {base_url}...")
    try:
        response = requests.get(base_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching inprint page: {e}")
        return None
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find monthly archive links - they're in a list with class "category-archives-block-list"
    archive_list = soup.find('ul', class_=re.compile(r'category-archives|archives', re.I))
    if not archive_list:
        # Try to find any links that look like monthly archives (e.g., "November 2025")
        archive_list = soup.find('ul')
    
    monthly_archive_url = None
    if archive_list:
        # Get the first (latest) monthly archive link
        first_link = archive_list.find('a', href=True)
        if first_link:
            monthly_archive_url = urljoin(base_url, first_link['href'])
            print(f"Step 2: Found latest monthly archive: {first_link.get_text(strip=True)}")
            print(f"  URL: {monthly_archive_url}")
    
    if not monthly_archive_url:
        print("Could not find monthly archive links on the inprint page.")
        return None
    
    # Step 2: Fetch the monthly archive page to find issue links
    print(f"Step 3: Fetching monthly archive page...")
    try:
        response = requests.get(monthly_archive_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching monthly archive page: {e}")
        return None
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find "Download issue" links
    issue_links = []
    for link in soup.find_all('a', href=True):
        link_text = link.get_text(strip=True).lower()
        if 'download issue' in link_text:
            href = link.get('href')
            if href:
                full_url = urljoin(monthly_archive_url, href)
                issue_links.append((link_text, full_url))
    
    if not issue_links:
        print("Could not find 'Download issue' links on the monthly archive page.")
        return None
    
    # Get the first (latest) issue link
    latest_issue_text, latest_issue_url = issue_links[0]
    print(f"Step 4: Found latest issue: {latest_issue_text}")
    print(f"  URL: {latest_issue_url}")
    
    # Step 3: Fetch the issue page to find the PDF
    print(f"Step 5: Fetching issue page...")
    try:
        response = requests.get(latest_issue_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching issue page: {e}")
        return None
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find the PDF in an <embed> tag
    pdf_url = None
    embed_tag = soup.find('embed', src=True)
    if embed_tag:
        pdf_url = embed_tag.get('src')
        if pdf_url:
            pdf_url = urljoin(latest_issue_url, pdf_url)
            print(f"Step 6: Found PDF in embed tag: {pdf_url}")
    
    # Fallback: Look for PDF in any element's src or data attributes
    if not pdf_url:
        for elem in soup.find_all(True):
            for attr in ['src', 'data-url', 'data-src', 'data-href']:
                value = elem.get(attr, '')
                if value and '.pdf' in str(value).lower():
                    pdf_url = urljoin(latest_issue_url, value)
                    print(f"Step 6: Found PDF in {elem.name}[{attr}]: {pdf_url}")
                    break
            if pdf_url:
                break
    
    if not pdf_url:
        print("Could not find PDF URL on the issue page.")
        return None
    
    # Step 4: Download the PDF
    print(f"Step 7: Downloading PDF from {pdf_url}...")
    try:
        pdf_response = requests.get(pdf_url, timeout=60, stream=True)
        pdf_response.raise_for_status()
        
        # Determine filename
        # Try to get filename from Content-Disposition header
        content_disposition = pdf_response.headers.get('Content-Disposition', '')
        if 'filename=' in content_disposition:
            filename = re.findall(r'filename="?([^"]+)"?', content_disposition)[0]
        else:
            # Extract from URL
            parsed_url = urlparse(pdf_url)
            filename = Path(parsed_url.path).name
            if not filename or not filename.endswith('.pdf'):
                # Generate a filename based on the issue URL
                filename = f"dorchester_reporter_{Path(urlparse(latest_issue_url).path).name}.pdf"
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

