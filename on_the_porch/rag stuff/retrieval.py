from langchain_community.vectorstores import Chroma
from pathlib import Path
from datetime import date
import os
import google.generativeai as genai  # type: ignore

VECTORDB_DIR = Path("../vectordb_new")
CALENDAR_VECTORDB_DIR = Path("../vectordb_calendar")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "models/text-embedding-004")


def _configure_gemini() -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    genai.configure(api_key=api_key)


class GeminiEmbeddings:
    """
    Minimal embeddings wrapper using Gemini's embedding API, compatible with LangChain's interface.
    """

    def __init__(self, model: str | None = None) -> None:
        _configure_gemini()
        self.model = model or GEMINI_EMBED_MODEL

    def _embed(self, text: str):
        res = genai.embed_content(model=self.model, content=text)
        return res["embedding"]

    def embed_documents(self, texts):
        return [self._embed(t) for t in texts]

    def embed_query(self, text):
        return self._embed(text)


def load_vectordb():
    """Load the main (policy + transcripts) vector database."""
    embeddings = GeminiEmbeddings()
    vectordb = Chroma(
        persist_directory=str(VECTORDB_DIR),
        embedding_function=embeddings,
    )
    return vectordb


def load_calendar_vectordb():
    """Load the separate calendar events vector database."""
    embeddings = GeminiEmbeddings()
    vectordb = Chroma(
        persist_directory=str(CALENDAR_VECTORDB_DIR),
        embedding_function=embeddings,
    )
    return vectordb


def _parse_iso_date(value: str):
    """Parse ISO date (YYYY-MM-DD) safely, return None on failure."""
    try:
        return date.fromisoformat(value)
    except Exception:
        return None


def retrieve(query, k=5, doc_type=None, tags=None, source=None, min_score=None, vectordb=None):
    """
    Universal retrieval with flexible metadata filtering.
    
    Args:
        query: Search query string
        k: Number of results to return
        doc_type: Filter by document type ('transcript', 'policy', or 'calendar_event')
        tags: Filter by tags (list of tags, e.g., ['media', 'community'])
               For transcripts only - uses OR logic (chunk must have ANY tag)
        source: Filter by specific source filename
        min_score: Optional minimum similarity score threshold (lower is more similar)
    
    Returns:
        dict with chunks, metadata, and optional scores
    
    Examples:
        # Only transcripts
        retrieve(query, doc_type='transcript')
        
        # Transcripts with specific tags
        retrieve(query, doc_type='transcript', tags=['media', 'community'])
        
        # Only policy docs
        retrieve(query, doc_type='policy')
        
        # Specific source file
        retrieve(query, source='Boston Anti-Displacement Plan Analysis.txt')
        
        # Everything
        retrieve(query)
    """
    if vectordb is None:
        vectordb = load_vectordb()
    
    # Build filter dictionary (Chroma requires $and for multiple conditions)
    filter_dict = None
    
    if doc_type and source:
        # Multiple filters - use $and
        filter_dict = {
            "$and": [
                {"doc_type": doc_type},
                {"source": source}
            ]
        }
    elif doc_type:
        filter_dict = {'doc_type': doc_type}
    elif source:
        filter_dict = {'source': source}
    
    # Note: Tag filtering is more complex in Chroma
    # For now, we'll filter tags in post-processing if specified
    # Chroma doesn't support list membership queries directly in filters
    
    # Retrieve with or without score threshold
    if min_score is not None:
        results_with_scores = vectordb.similarity_search_with_score(
            query, 
            k=k * 3 if tags else k,  # Get more if we need to filter tags
            filter=filter_dict if filter_dict else None
        )
        
        # Post-process tag filtering if needed (soft filter: fall back to unfiltered if no matches)
        if tags:
            filtered_results = []
            for doc, score in results_with_scores:
                if 'tags' in doc.metadata:
                    # Tags stored as comma-separated string
                    doc_tags = [t.strip() for t in doc.metadata['tags'].split(',')]
                    # Check if ANY requested tag is in document tags (OR logic)
                    if any(tag in doc_tags for tag in tags):
                        filtered_results.append((doc, score))
                        if len(filtered_results) >= k:
                            break
            # Only apply tag filter if it yields at least one result
            if filtered_results:
                results_with_scores = filtered_results
        
        # Apply score threshold
        filtered_results = [(doc, score) for doc, score in results_with_scores if score <= min_score]
        
        return {
            'chunks': [doc.page_content for doc, _ in filtered_results[:k]],
            'metadata': [doc.metadata for doc, _ in filtered_results[:k]],
            'scores': [score for _, score in filtered_results[:k]],
            'query': query
        }
    else:
        results = vectordb.similarity_search(
            query, 
            k=k * 3 if tags else k,
            filter=filter_dict if filter_dict else None
        )
        
        # Post-process tag filtering if needed (soft filter: fall back to unfiltered if no matches)
        if tags:
            filtered_results = []
            for doc in results:
                if 'tags' in doc.metadata:
                    # Tags stored as comma-separated string
                    doc_tags = [t.strip() for t in doc.metadata['tags'].split(',')]
                    # Check if ANY requested tag is in document tags (OR logic)
                    if any(tag in doc_tags for tag in tags):
                        filtered_results.append(doc)
                        if len(filtered_results) >= k:
                            break
            # Only apply tag filter if it yields at least one result
            if filtered_results:
                results = filtered_results
        
        return {
            'chunks': [doc.page_content for doc in results[:k]],
            'metadata': [doc.metadata for doc in results[:k]],
            'scores': None,
            'query': query
        }


def retrieve_transcripts(query, tags=None, k=5):
    """
    Convenience function for transcript-only search.
    
    Args:
        query: Search query
        tags: Optional list of tags to filter by (e.g., ['media', 'community'])
        k: Number of results
    
    Example:
        retrieve_transcripts("What do people say about safety?", tags=['safety'])
    """
    return retrieve(query, k=k, doc_type='transcript', tags=tags)


def retrieve_policies(query, k=5, source=None):
    """
    Convenience function for policy-only search.
    
    Args:
        query: Search query
        k: Number of results
        source: Optional specific policy document to search
    
    Example:
        retrieve_policies("anti-displacement strategies")
    """
    return retrieve(query, k=k, doc_type='policy', source=source)


def retrieve_calendar_events(query, k=5, start_date: str | None = None, end_date: str | None = None):
    """
    Convenience function for calendar-event-only search.

    Args:
        query: Search query
        k: Number of results

    Example:
        retrieve_calendar_events("What events are happening this week?", k=5)
        retrieve_calendar_events("events", start_date="2025-03-01", end_date="2025-03-07")
    """
    calendar_db = load_calendar_vectordb()

    # If no date filters, just delegate to generic retrieval.
    if not start_date and not end_date:
        return retrieve(query, k=k, doc_type='calendar_event', vectordb=calendar_db)

    # With date filters, get a few extra candidates then filter by overlap.
    base = retrieve(query, k=k * 3, doc_type='calendar_event', vectordb=calendar_db)

    q_start = _parse_iso_date(start_date) if start_date else None
    q_end = _parse_iso_date(end_date) if end_date else None

    filtered_chunks = []
    filtered_meta = []

    for chunk, meta in zip(base["chunks"], base["metadata"]):
        ev_start = _parse_iso_date(str(meta.get("start_date") or "")) if meta.get("start_date") else None
        ev_end = _parse_iso_date(str(meta.get("end_date") or "")) if meta.get("end_date") else None

        # Treat missing end_date as same-day event.
        if ev_start and not ev_end:
            ev_end = ev_start
        if ev_end and not ev_start:
            ev_start = ev_end

        if not ev_start and not ev_end:
            continue

        include = False
        # Overlap logic between [ev_start, ev_end] and [q_start, q_end]
        if q_start and q_end:
            include = ev_end >= q_start and ev_start <= q_end
        elif q_start:
            include = ev_start <= q_start <= ev_end
        elif q_end:
            include = ev_start <= q_end <= ev_end

        if include:
            filtered_chunks.append(chunk)
            filtered_meta.append(meta)
            if len(filtered_chunks) >= k:
                break

    # If nothing matched filters, fall back to unfiltered base results (top-k).
    if not filtered_chunks:
        return base

    return {
        "chunks": filtered_chunks,
        "metadata": filtered_meta,
        "scores": base.get("scores"),
        "query": query,
    }


def format_results(result_dict):
    """Format retrieval results for display."""
    formatted = []
    formatted.append(f"Query: {result_dict['query']}")
    formatted.append(f"Total results: {len(result_dict['chunks'])}\n")
    
    for i, (chunk, meta) in enumerate(zip(result_dict['chunks'], result_dict['metadata']), 1):
        formatted.append(f"\n{'='*80}")
        formatted.append(f"Result {i}")
        formatted.append(f"Source: {meta.get('source', 'Unknown')}")
        formatted.append(f"Type: {meta.get('doc_type', 'Unknown')}")
        
        if meta.get('tags'):
            formatted.append(f"Tags: {meta['tags']}")
        if meta.get('Heading'):
            formatted.append(f"Section: {meta['Heading']}")
        
        if result_dict.get('scores'):
            formatted.append(f"Score: {result_dict['scores'][i-1]:.4f}")
        
        formatted.append(f"\nContent:\n{chunk[:300]}...")
    
    return '\n'.join(formatted)


if __name__ == "__main__":
    # Example usage
    print("=== Example 1: Search transcripts only ===")
    results = retrieve_transcripts("What do people say about media representation?", k=3)
    print(format_results(results))
    
    print("\n\n=== Example 2: Search with specific tags ===")
    results = retrieve_transcripts("community safety", tags=['safety'], k=3)
    print(format_results(results))
    
    print("\n\n=== Example 3: Search policy docs ===")
    results = retrieve_policies("housing affordability", k=3)
    print(format_results(results))
