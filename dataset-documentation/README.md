# Dataset Documentation

This directory contains comprehensive documentation for all datasets used in the RethinkAI Community Sentiment Analysis Platform.

## Overview

The platform uses a hybrid data architecture combining structured (SQL) and unstructured (vector) data sources to provide comprehensive community insights.

## Data Sources

### 1. Boston 311 Service Requests

**Source**: City of Boston Open Data Portal  
**Format**: MySQL database table  
**Update Frequency**: Daily sync via `on_the_porch/data_ingestion/boston_data_sync/`

**Schema**:
- `id`: Unique request identifier
- `case_enquiry_id`: Official 311 case ID
- `open_dt`: Request open date/time
- `closed_dt`: Request closed date/time (if applicable)
- `case_status`: Status (Open, Closed, etc.)
- `subject`: Request subject
- `reason`: Request reason/category
- `type`: Request type
- `latitude`, `longitude`: Geographic coordinates
- `neighborhood`: Boston neighborhood
- `zipcode`: ZIP code

**Categories**:
- Living Conditions
- Trash, Recycling, And Waste
- Streets, Sidewalks, And Parks
- Parking

**Usage**: Queryable via SQL for geospatial and temporal analysis.

**Example Queries**:
- "Show me all pothole requests in Dorchester from last month"
- "What are the most common 311 requests in zipcode 02125?"

### 2. Boston 911 Emergency Reports

**Source**: City of Boston Open Data Portal  
**Format**: MySQL database table  
**Update Frequency**: Daily sync via `on_the_porch/data_ingestion/boston_data_sync/`

**Schema**:
- `id`: Unique report identifier
- `incident_type_description`: Type of incident
- `occurred_on_date`: Date/time of incident
- `latitude`, `longitude`: Geographic coordinates
- `shooting`: Boolean flag for shooting incidents
- `district`: Police district

**Subsets**:
- Shots fired incidents
- Homicides and shootings
- All incidents

**Usage**: Queryable via SQL for crime analysis and public safety insights.

**Example Queries**:
- "How many shootings occurred in Dorchester last year?"
- "Show me all incidents near [address] in the past month"

### 3. Community Events

**Source**: Extracted from community newsletters via email sync  
**Format**: MySQL database table (`weekly_events`)  
**Update Frequency**: Daily via `on_the_porch/data_ingestion/`

**Schema**:
- `id`: Unique event identifier
- `event_name`: Name of the event
- `event_date`: Date string
- `start_date`, `end_date`: Date objects
- `start_time`, `end_time`: Time objects
- `raw_text`: Original text from newsletter
- `source_pdf`: Source document identifier

**Usage**: Queryable via SQL for temporal queries and calendar functionality.

**Example Queries**:
- "What events are happening this weekend?"
- "Show me all workshops in December"

### 4. Community Documents (Vector Database)

**Source**: Google Drive folder + Email newsletters  
**Format**: ChromaDB vector database  
**Update Frequency**: Daily sync via `on_the_porch/data_ingestion/`

**Document Types**:
- PDF newsletters
- Meeting transcripts
- Policy documents
- Community announcements
- Budget documents
- Planning documents

**Storage**: 
- **Events** → Extracted to MySQL (`weekly_events` table)
- **Articles/News** → Stored in vector database for semantic search

**Usage**: Queryable via RAG (Retrieval-Augmented Generation) for semantic search.

**Example Queries**:
- "What's the latest news about affordable housing?"
- "Tell me about community safety initiatives"
- "What was discussed in the last community meeting?"

### 5. Geospatial Community Assets

**Source**: Community-curated data  
**Format**: GeoJSON files  
**Location**: `api/datastore/geocoding-community-assets.csv`

**Content**:
- Community centers
- Schools
- Parks
- Businesses
- Places of worship
- Other community landmarks

**Usage**: Used for map visualizations and geospatial context.

## Data Quality Notes

### 311 Data
- **Completeness**: High - most requests have location data
- **Timeliness**: Updated daily
- **Accuracy**: Subject to reporting bias (underreporting in some areas)
- **Geocoding**: Some addresses may have missing or inaccurate coordinates

### 911 Data
- **Completeness**: High for reported incidents
- **Timeliness**: Updated daily
- **Accuracy**: Official police records
- **Limitations**: Does not include all crime (only reported incidents)

### Community Events
- **Completeness**: Depends on newsletter coverage
- **Timeliness**: Extracted daily from new newsletters
- **Accuracy**: Extracted via LLM, may have parsing errors
- **Coverage**: Only events mentioned in synced newsletters

### Community Documents
- **Completeness**: Depends on Google Drive folder contents
- **Timeliness**: Synced daily
- **Accuracy**: Original documents, no modification
- **Coverage**: Limited to documents in shared folder

## Data Access Patterns

### SQL Queries (Structured Data)
- **311 Requests**: Filtered by date, location, category
- **911 Reports**: Filtered by date, location, incident type
- **Events**: Filtered by date range, event type

### RAG Queries (Unstructured Data)
- **Semantic Search**: Finds relevant documents by meaning
- **Context Retrieval**: Returns relevant chunks with citations
- **Hybrid Mode**: Combines SQL results with document context

## Data Updates

### Automated Sync Process

1. **Boston Data Sync** (`on_the_porch/data_ingestion/boston_data_sync/`)
   - Runs daily via cron job
   - Syncs 311 and 911 data from city APIs
   - Updates MySQL database

2. **Google Drive Sync** (`on_the_porch/data_ingestion/`)
   - Monitors Google Drive folder for new/changed files
   - Processes PDF, DOCX, TXT, MD files
   - Updates vector database

3. **Email Newsletter Sync** (`on_the_porch/data_ingestion/`)
   - Checks email inbox daily
   - Extracts events → MySQL
   - Extracts articles → Vector DB

### Manual Updates

- Community assets: Update CSV file in `api/datastore/`
- Static documents: Add to Google Drive folder
- Database schema: See `on_the_porch/new_metadata/` for metadata generation

## Data Retention

- **311 Data**: All historical data retained
- **911 Data**: All historical data retained
- **Events**: Retained indefinitely (archived events remain queryable)
- **Documents**: All documents retained in vector database

## Privacy & Ethics

- **Public Data**: 311 and 911 data are public records
- **Anonymization**: No personal information stored
- **Community Documents**: Only publicly shared documents
- **Usage**: Data used for community insights and public safety analysis

## Schema Metadata

For detailed database schemas, see:
- `on_the_porch/new_metadata/` - Auto-generated schema metadata
- MySQL metadata: Generated via `generate_mysql_metadata_live.py`

## Example Data Queries

### SQL Examples

```sql
-- 311 requests by category
SELECT normalized_type, COUNT(*) as total
FROM boston_311
WHERE open_dt >= DATE_SUB(NOW(), INTERVAL 1 MONTH)
GROUP BY normalized_type;

-- Events this week
SELECT event_name, start_date, start_time
FROM weekly_events
WHERE start_date >= CURDATE()
  AND start_date <= DATE_ADD(CURDATE(), INTERVAL 7 DAY)
ORDER BY start_date, start_time;
```

### RAG Examples

```python
# Semantic search for housing information
query = "affordable housing initiatives"
results = retrieval.search(query, top_k=5)
```

## Troubleshooting

### Missing Data
- Check sync logs: `on_the_porch/data_ingestion/ingestion_log.jsonl`
- Verify API keys and credentials
- Check database connection

### Data Quality Issues
- Review extraction logs for event parsing errors
- Verify geocoding accuracy for location data
- Check vector database for document indexing issues

## References

- Boston Open Data Portal: https://data.boston.gov
- Data Ingestion Documentation: `on_the_porch/data_ingestion/README.md`
- API Documentation: `api/README.md`

