# RAG Vector Database System

This folder contains a vector database and retrieval system for the community sentiment RAG application.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file with your OpenAI API key:
```bash
OPENAI_API_KEY=your_api_key_here
```

## Building the Vector Database

Run the build script to process all text files in the `Data/` folder:

```bash
python build_vectordb.py
```

This will:
- Load all `.txt` files from the `Data/` directory
- Split them using `MarkdownHeaderTextSplitter` which automatically extracts # ## ### as metadata
- Further split large chunks with `RecursiveCharacterTextSplitter` (chunk_size=1000, overlap=200)
- Create embeddings using OpenAI
- Store everything in a ChromaDB vector database

## Using the Retrieval System

```python
from retrieval import retrieve_documents, format_results

# Basic retrieval
results = retrieve_documents("What is the anti-displacement plan?", k=5)
print(format_results(results))

# Filter by source file
results = retrieve_documents(
    "traffic safety", 
    k=3, 
    filter_metadata={'source': 'Boston Slow Streets Plan Analysis.txt'}
)

# Get results with similarity scores
from retrieval import retrieve_with_scores
results_with_scores = retrieve_with_scores("community engagement", k=3)
for doc, score in results_with_scores:
    print(f"Score: {score}")
    print(f"Content: {doc.page_content[:100]}...")
```

## Metadata Structure

Each document chunk includes:
- `source`: Original filename
- `Header 1`: Content of H1 heading (# in markdown)
- `Header 2`: Content of H2 heading (## in markdown)
- `Header 3`: Content of H3 heading (### in markdown)

The `MarkdownHeaderTextSplitter` automatically extracts these headers and adds them as metadata, making it easy to filter and provide context during retrieval.

## Files

- `build_vectordb.py`: Script to build the vector database
- `retrieval.py`: Functions for querying the vector database
- `Data/`: Source text files
- `vectordb/`: ChromaDB storage (created after running build script)

