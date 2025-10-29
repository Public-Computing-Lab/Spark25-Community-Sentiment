import re
from pathlib import Path
from langchain.schema import Document

def parse_transcript_chunks(file_path):
    """
    Parse AI meeting transcript file and extract chunks with tags.
    
    Format:
    [1]
    quote text
    [Highlight]
    
    [Comments]
    Person Name: tag1, tag2
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by chunk numbers [1], [2], etc.
    # Pattern: [\d+] at start of line
    chunk_pattern = r'\[(\d+)\](.*?)(?=\[\d+\]|$)'
    chunks = re.findall(chunk_pattern, content, re.DOTALL)
    
    documents = []
    
    for chunk_num, chunk_content in chunks:
        # Extract the quote text (before [Highlight])
        quote_match = re.search(r'(.*?)\[Highlight\]', chunk_content, re.DOTALL)
        if not quote_match:
            continue
        
        quote_text = quote_match.group(1).strip()
        
        # Skip empty quotes
        if not quote_text:
            continue
        
        # Extract tags from [Comments] section
        # Pattern: after the colon, before newline
        tags_match = re.search(r'\[Comments\].*?:\s*(.+?)(?:\n|$)', chunk_content, re.DOTALL)
        
        tags = []
        if tags_match:
            # Extract tags, split by comma, clean up
            tags_text = tags_match.group(1).strip()
            tags = [tag.strip().lower() for tag in tags_text.split(',')]
        
        # Create metadata
        metadata = {
            'source': Path(file_path).name,
            'doc_type': 'transcript',
            'chunk_id': int(chunk_num),
        }
        
        # Only add tags if they exist
        if tags:
            metadata['tags'] = tags
        
        # Create document
        doc = Document(
            page_content=quote_text,
            metadata=metadata
        )
        documents.append(doc)
    
    return documents


if __name__ == "__main__":
    # Test with one file
    test_file = Path("Data/AI meeting transcripts/8_31 Journalists_otter_ai.txt")
    
    print(f"Parsing: {test_file.name}\n")
    docs = parse_transcript_chunks(test_file)
    
    print(f"Found {len(docs)} chunks\n")
    print("="*80)
    
    # Show first 3 chunks
    for i, doc in enumerate(docs[:3], 1):
        print(f"\n--- Chunk {i} ---")
        print(f"Content: {doc.page_content[:200]}...")
        print(f"Metadata: {doc.metadata}")
    
    print(f"\n{'='*80}")
    print(f"\nTotal chunks parsed: {len(docs)}")
    
    # Show tag distribution
    all_tags = []
    chunks_with_tags = 0
    chunks_without_tags = 0
    
    for doc in docs:
        if 'tags' in doc.metadata:
            all_tags.extend(doc.metadata['tags'])
            chunks_with_tags += 1
        else:
            chunks_without_tags += 1
    
    print(f"Chunks with tags: {chunks_with_tags}")
    print(f"Chunks without tags: {chunks_without_tags}")
    
    # Count unique tags
    from collections import Counter
    tag_counts = Counter(all_tags)
    print(f"\nTag distribution:")
    for tag, count in tag_counts.most_common():
        print(f"  {tag}: {count}")

