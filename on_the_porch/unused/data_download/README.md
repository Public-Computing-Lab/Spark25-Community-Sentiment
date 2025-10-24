# Boston 911 Data Downloader & Importer

This folder contains scripts to download 911 data from Boston's open data portal and import it into your MySQL database.

## Files

- `download_911_data.py` - Downloads 911 data from Boston API
- `import_911_to_mysql.py` - Imports the data into MySQL
- `requirements.txt` - Python dependencies

## Quick Start

1. Install dependencies: `pip install -r requirements.txt`
2. Download data: `python download_911_data.py`
3. Import to MySQL: `python import_911_to_mysql.py`

## Data Sources

- **Boston Open Data Portal**: https://data.boston.gov/
- **Crime Data Resource ID**: 12cb3883-56f5-47de-afa5-3b1cf61bb257

## Database Tables Created

- `shots_fired_data` - Shots fired incidents
- `homicide_data` - Homicide incidents

## Notes

- Data is filtered for Dorchester area (districts B2, B3, C11)
- Coordinates are cleaned and validated
- Duplicate records are handled with ON DUPLICATE KEY UPDATE
