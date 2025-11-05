"""
Example usage of the vector database retrieval system.
"""

from retrieval import retrieve_documents, retrieve_with_scores, format_results
from dotenv import load_dotenv

load_dotenv()


def example_basic_search():
    """Basic search example."""
    print("="*80)
    print("EXAMPLE 1: Basic Search")
    print("="*80)
    
    query = "What is the anti-displacement plan?"
    results = retrieve_documents(query, k=3)
    print(format_results(results))


def example_filtered_search():
    """Search filtered by source document."""
    print("\n" + "="*80)
    print("EXAMPLE 2: Filtered Search")
    print("="*80)
    
    query = "traffic safety measures"
    results = retrieve_documents(
        query, 
        k=3, 
        filter_metadata={'source': 'Boston Slow Streets Plan Analysis.txt'}
    )
    print(format_results(results))


def example_with_scores():
    """Search with similarity scores."""
    print("\n" + "="*80)
    print("EXAMPLE 3: Search with Scores")
    print("="*80)
    
    query = "community engagement"
    results = retrieve_with_scores(query, k=3)
    
    for i, (doc, score) in enumerate(results, 1):
        print(f"\n{'='*80}")
        print(f"Result {i} - Similarity Score: {score:.4f}")
        print(f"Source: {doc.metadata.get('source', 'Unknown')}")
        
        if doc.metadata.get('Sub Heading'):
            print(f"Section: {doc.metadata['Sub Heading']}")
        
        print(f"\nContent Preview:\n{doc.page_content[:200]}...")


def example_specific_topics():
    """Search for specific topics."""
    print("\n" + "="*80)
    print("EXAMPLE 4: Multiple Topic Searches")
    print("="*80)
    
    queries = [
        "housing affordability",
        "small business support",
        "transportation improvements",
    ]
    
    for query in queries:
        print(f"\n--- Query: {query} ---")
        results = retrieve_documents(query, k=2)
        
        for doc in results:
            print(f"\nSource: {doc.metadata.get('source')}")
            print(f"H2: {doc.metadata.get('Sub Heading', 'N/A')}")
            print(f"Preview: {doc.page_content[:150]}...")


if __name__ == "__main__":
    print("Vector Database Retrieval Examples\n")
    
    example_basic_search()
    example_filtered_search()
    example_with_scores()
    example_specific_topics()

