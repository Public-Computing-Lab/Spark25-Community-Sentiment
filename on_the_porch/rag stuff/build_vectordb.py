from pathlib import Path
import re

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()
POLICY_DIR = Path("Data/VectorDB_text")
TRANSCRIPT_DIR = Path("Data/AI meeting transcripts")
VECTORDB_DIR = Path("../vectordb_new")


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
        tags_match = re.search(r'\[Comments\].*?:\s*(.+?)(?:\n|$)', chunk_content, re.DOTALL)
        
        tags = []
        if tags_match:
            tags_text = tags_match.group(1).strip()
            tags = [tag.strip().lower() for tag in tags_text.split(',')]
        
        # Create metadata
        metadata = {
            'source': Path(file_path).name,
            'doc_type': 'transcript',
            'chunk_id': int(chunk_num),
        }
        
        # Only add tags if they exist (convert list to comma-separated string)
        if tags:
            metadata['tags'] = ', '.join(tags)
        
        # Create document
        doc = Document(
            page_content=quote_text,
            metadata=metadata
        )
        documents.append(doc)
    
    return documents


def load_policy_documents():
    """Load policy documents with markdown header metadata."""
    documents = []
    
    text_files = list(POLICY_DIR.glob("*.txt"))
    print(f"Found {len(text_files)} policy files")
    
    # Define headers to split on
    headers_to_split_on = [
        ("#", "Heading"),
        ("##", "Sub Heading")
    ]
    
    # Markdown splitter to split by headers and add as metadata
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False
    )
    
    for file_path in text_files:
        print(f"Processing policy: {file_path.name}...")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by markdown headers
        md_header_splits = markdown_splitter.split_text(content)
        
        for doc in md_header_splits:
            doc.metadata['source'] = file_path.name
            doc.metadata['doc_type'] = 'policy'
            documents.append(doc)
    
    print(f"Created {len(documents)} policy chunks")
    return documents


def load_transcript_documents():
    """Load and parse AI meeting transcripts with tags."""
    documents = []
    
    transcript_files = list(TRANSCRIPT_DIR.glob("*.txt"))
    print(f"Found {len(transcript_files)} transcript files")
    
    for file_path in transcript_files:
        print(f"Processing transcript: {file_path.name}...")
        chunks = parse_transcript_chunks(file_path)
        documents.extend(chunks)
    
    print(f"Created {len(documents)} transcript chunks")
    return documents


def build_vectordb():
    """Build the vector database from policy and transcript documents."""
    # Load documents
    policy_docs = load_policy_documents()
    transcript_docs = load_transcript_documents()

    all_documents = policy_docs + transcript_docs

    print(f"\n{'='*80}")
    print(f"Total documents: {len(all_documents)}")
    print(f"  - Policy chunks: {len(policy_docs)}")
    print(f"  - Transcript chunks: {len(transcript_docs)}")

    # Show tag stats for transcripts
    tagged_count = sum(1 for doc in transcript_docs if 'tags' in doc.metadata)
    print(f"  - Transcript chunks with tags: {tagged_count}")
    print(f"  - Transcript chunks without tags: {len(transcript_docs) - tagged_count}")
    print(f"{'='*80}\n")
    
    embeddings = OpenAIEmbeddings()
    
    if VECTORDB_DIR.exists():
        print(f"Removing existing vector database at {VECTORDB_DIR}")
        import shutil
        shutil.rmtree(VECTORDB_DIR)
    
    print(f"Building vector database at {VECTORDB_DIR}")
    vectordb = Chroma.from_documents(
        documents=all_documents,
        embedding=embeddings,
        persist_directory=str(VECTORDB_DIR),
    )
    
    print("Vector database built successfully!")
    return vectordb


if __name__ == "__main__":
    build_vectordb()

