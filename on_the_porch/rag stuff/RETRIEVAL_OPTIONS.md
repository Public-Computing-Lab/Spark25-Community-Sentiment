# Vector Database Retrieval Options

Complete guide to all retrieval and filtering options available with your setup.

---

## 1. **Basic Similarity Search**
Get top-k most similar documents.

```python
from retrieval import retrieve_policy_context

result = retrieve_policy_context(
    query="anti-displacement strategies",
    k=5  # Number of results
)
```

**When to use:** Default option for most queries.

---

## 2. **Filter by Source Document**
Retrieve from only one specific policy document.

```python
result = retrieve_policy_context(
    query="housing affordability",
    k=3,
    filter_source="Boston Anti-Displacement Plan Analysis.txt"
)
```

**Available sources:**
- `"Boston Anti-Displacement Plan Analysis.txt"`
- `"Boston Slow Streets Plan Analysis.txt"`
- `"Imagine Boston 2030 Analysis.txt"`

**When to use:** When you know which policy document is relevant (e.g., router indicates specific plan).

---

## 3. **Similarity Score Threshold**
Only return results above a certain quality threshold.

```python
result = retrieve_policy_context(
    query="transportation improvements",
    k=10,
    min_score=0.7  # Only results with distance score ≤ 0.7
)
```

**Score interpretation:**
- Lower = more similar (0 = identical)
- Typical good matches: 0.3 - 0.8
- Higher = less relevant

**When to use:** When you want to filter out low-quality matches. Good for avoiding irrelevant context.

---

## 4. **Metadata Filtering** (Advanced)
Filter by any metadata field (not just source).

```python
from retrieval import retrieve_documents

# Filter by markdown header
results = retrieve_documents(
    query="community engagement",
    k=5,
    filter_metadata={
        'Header 1': 'Overview',  # Only sections under this H1
    }
)

# Multiple filters (AND logic)
results = retrieve_documents(
    query="housing programs",
    k=5,
    filter_metadata={
        'source': 'Boston Anti-Displacement Plan Analysis.txt',
        'Header 2': 'The "Protect" Pillar'  # Specific section
    }
)
```

**Available metadata fields:**
- `source`: Filename
- `Header 1`: Top-level markdown headers
- `Header 2`: Second-level headers

**When to use:** When you need granular control over which sections to search.

---

## 5. **MMR (Maximum Marginal Relevance)**
Get diverse results instead of all similar ones.

```python
from retrieval import load_vectordb

vectordb = load_vectordb()

results = vectordb.max_marginal_relevance_search(
    query="community programs",
    k=5,
    fetch_k=20,  # Fetch 20 candidates first
    lambda_mult=0.5  # 0=max diversity, 1=max relevance
)
```

**Parameters:**
- `lambda_mult=0.7`: Favor relevance (more similar results)
- `lambda_mult=0.3`: Favor diversity (different topics)

**When to use:** When you want a broad overview covering different aspects, not repetitive similar content.

---

## 6. **Multi-Query Retrieval**
Search with multiple related queries, merge results.

```python
from retrieval import retrieve_policy_context

queries = [
    "housing affordability programs",
    "anti-displacement initiatives", 
    "rental protection policies"
]

all_results = []
seen_chunks = set()

for q in queries:
    result = retrieve_policy_context(q, k=3)
    for chunk in result['chunks']:
        if chunk not in seen_chunks:
            all_results.append(chunk)
            seen_chunks.add(chunk)

# Deduplicated results from multiple queries
```

**When to use:** Complex questions that have multiple facets.

---

## 7. **Query Expansion with LLM**
Let LLM generate better search queries.

```python
from openai import OpenAI

client = OpenAI()

# Generate better query
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{
        "role": "user",
        "content": f"Rephrase this query to better search policy documents: '{user_query}'"
    }]
)
expanded_query = response.choices[0].message.content

# Use expanded query
result = retrieve_policy_context(expanded_query, k=5)
```

**When to use:** When user query is vague or uses different terminology than policy docs.

---

## 8. **Combining Multiple Filters**
Metadata filtering with score threshold.

```python
from retrieval import load_vectordb

vectordb = load_vectordb()

results_with_scores = vectordb.similarity_search_with_score(
    query="budget allocations",
    k=10,
    filter={'source': 'Boston Anti-Displacement Plan Analysis.txt'}
)

# Filter by score after retrieval
good_results = [
    (doc, score) for doc, score in results_with_scores 
    if score <= 0.75
]
```

**When to use:** Need both document filtering AND quality threshold.

---

## 9. **Search by Embedding (No Text)**
If you already have an embedding vector.

```python
vectordb = load_vectordb()

# If you have a pre-computed embedding
embedding_vector = [0.1, 0.2, ...]  # 1536 dims for OpenAI

results = vectordb.similarity_search_by_vector(
    embedding=embedding_vector,
    k=5
)
```

**When to use:** Rare - when you have embeddings from another system.

---

## 10. **Fetch All Metadata First, Then Filter**
Understand what's available before searching.

```python
vectordb = load_vectordb()

# Get collection stats
collection = vectordb._collection
count = collection.count()
print(f"Total chunks: {count}")

# Sample some documents to see metadata
sample = vectordb.similarity_search("housing", k=3)
for doc in sample:
    print(doc.metadata)
```

**When to use:** Debugging or understanding your data structure.

---

## Recommended Workflow Integration

### In your node workflow:

```python
def vector_retrieval_node(state):
    query = state.get("vector_query")  # From router
    user_query = state.get("user_query")
    
    # Strategy 1: Basic (most cases)
    if state.get("simple_query"):
        result = retrieve_policy_context(query, k=5)
    
    # Strategy 2: Filtered by document (when router specifies)
    elif state.get("target_document"):
        result = retrieve_policy_context(
            query, 
            k=5,
            filter_source=state["target_document"]
        )
    
    # Strategy 3: High quality only
    elif state.get("high_precision_needed"):
        result = retrieve_policy_context(
            query,
            k=10,
            min_score=0.6
        )
    
    # Strategy 4: Diverse results
    else:
        vectordb = load_vectordb()
        docs = vectordb.max_marginal_relevance_search(
            query, k=5, lambda_mult=0.5
        )
        result = {
            'chunks': [doc.page_content for doc in docs],
            'metadata': [doc.metadata for doc in docs]
        }
    
    state["policy_context"] = result
    return state
```

---

## Performance Tips

1. **Start with k=5**: Good balance of context and speed
2. **Use min_score=0.8** to filter weak matches
3. **Filter by source** when possible (faster than searching all docs)
4. **MMR for summaries**, similarity for specific answers
5. **Cache results** if same query appears multiple times

---

## When NOT to Use Vector Search

- **Exact matches**: Use keyword search/grep
- **Structured queries**: Use SQL for your 311/911 data
- **Numerical comparisons**: Use SQL aggregations
- **Time-based queries**: SQL is better

Vector search is for **semantic meaning**, not exact/structured data.


