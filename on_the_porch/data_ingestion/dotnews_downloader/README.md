# Dorchester Reporter PDF Downloader

This module downloads the latest PDF issue from the Dorchester Reporter's inprint page (https://www.dotnews.com/inprint/).

## Usage

### As a script:
```bash
python -m on_the_porch.data_ingestion.dotnews_downloader.download_latest_pdf
```

### As a module:
```python
from on_the_porch.data_ingestion.dotnews_downloader import download_latest_pdf
from pathlib import Path

# Download to a specific directory
output_path = download_latest_pdf(
    base_url="https://www.dotnews.com/inprint/",
    output_dir=Path("./downloads")
)
```

## How it works

The script follows the website's structure:
1. Fetches the HTML from the `/inprint/` page using `requests`
2. Finds the latest monthly archive link (e.g., "November 2025")
3. Fetches that monthly archive page
4. Finds the latest "Download issue" link
5. Fetches that individual issue page
6. Finds the PDF URL in an `<embed>` tag
7. Downloads the PDF and saves it to the specified output directory

No Selenium required - just standard HTTP requests and HTML parsing.

## Dependencies

- `requests` (already in main requirements.txt)
- `beautifulsoup4` (already in data_ingestion/requirements.txt)

