from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from pathlib import Path

VECTORDB_DIR = Path("../vectordb_new")


def load_vectordb():
    """Load the existing vector database."""
    embeddings = OpenAIEmbeddings()
    vectordb = Chroma(
        persist_directory=str(VECTORDB_DIR),
        embedding_function=embeddings,
    )
    return vectordb


def retrieve(query, k=5, doc_type=None, tags=None, source=None, min_score=None):
    """
    Universal retrieval with flexible metadata filtering.
    
    Args:
        query: Search query string
        k: Number of results to return
        doc_type: Filter by document type ('transcript' or 'policy')
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
        
        # Post-process tag filtering if needed
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
        
        # Post-process tag filtering if needed
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
