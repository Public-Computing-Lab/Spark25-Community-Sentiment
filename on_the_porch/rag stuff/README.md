# RAG Retrieval System

Vector database and semantic retrieval for community documents, policies, and transcripts.

## What This Does

Provides semantic search over unstructured text data:
- Community meeting transcripts
- Policy documents (Anti-Displacement, Slow Streets, Imagine Boston 2030)
- Client-uploaded documents

## Key Files

- `retrieval.py` - Main retrieval functions (used by unified_chatbot.py)
- `build_vectordb.py` - Builds vector database from Data/ folder
- `Data/` - Source documents
- `vectordb_new/` - Chroma vector database (generated)

---

## Usage

### Basic Similarity Search

Get top-k most similar documents:

```python
from retrieval import retrieve

result = retrieve(
    query="anti-displacement strategies",
    k=5  # Number of results
)
```

### Filter by Document Type

Search only specific document types:

```python
# Policy documents only
result = retrieve(
    query="housing affordability",
    k=3,
    doc_type='policy'
)

# Transcripts only
result = retrieve(
    query="community concerns",
    k=3,
    doc_type='transcript'
)
```

### Filter by Source Document

Search a specific source file:

```python
result = retrieve(
    query="transportation improvements",
    k=3,
    source="Boston Slow Streets Plan Analysis.txt"
)
```

**Available policy sources:**
- `"Boston Anti-Displacement Plan Analysis.txt"`
- `"Boston Slow Streets Plan Analysis.txt"`
- `"Imagine Boston 2030 Analysis.txt"`

### Score Threshold

Only return high-quality matches:

```python
result = retrieve(
    query="community programs",
    k=10,
    min_score=0.8  # Lower score = more similar (0 = identical)
)
```

### Convenience Functions

```python
from retrieval import retrieve_policies, retrieve_transcripts

# Policy search
policies = retrieve_policies("anti-displacement strategies", k=5)

# Transcript search with tags
transcripts = retrieve_transcripts("safety concerns", tags=['safety'], k=5)
```

### MMR (Diverse Results)

Get diverse results instead of similar ones:

```python
from retrieval import load_vectordb

vectordb = load_vectordb()
results = vectordb.max_marginal_relevance_search(
    query="community programs",
    k=5,
    lambda_mult=0.5  # 0=max diversity, 1=max relevance
)
```

---

## When NOT to Use Vector Search

- **Exact matches** - Use keyword search
- **Structured queries** - Use SQL for 311/911 data
- **Numerical comparisons** - Use SQL aggregations
- **Time-based queries** - SQL is better for dates/times

Vector search is for **semantic meaning**, not exact/structured data.

---

## Performance Tips

1. Start with `k=5` for balance of context and speed
2. Use `min_score=0.8` to filter weak matches
3. Filter by source when possible (faster)
4. Use MMR for summaries, similarity for specific answers
