from pathlib import Path
import re
import os
import json

from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from dotenv import load_dotenv
from pypdf import PdfReader
import google.generativeai as genai  # type: ignore

from retrieval import GeminiEmbeddings

load_dotenv()

# Input directories
POLICY_DIR = Path("Data/VectorDB_text")
TRANSCRIPT_DIR = Path("Data/AI meeting transcripts")
NEWSLETTER_DIR = Path("Data/newsletters")

# Shared vector DB used by the chatbot
VECTORDB_DIR = Path("../vectordb_mixed")


def _get_gemini_client():
    """Minimal Gemini client helper for newsletter event extraction."""
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    genai.configure(api_key=api_key)
    return genai, model_name


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

    if not POLICY_DIR.exists() or not POLICY_DIR.is_dir():
        return documents

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

    if not TRANSCRIPT_DIR.exists() or not TRANSCRIPT_DIR.is_dir():
        return documents

    transcript_files = list(TRANSCRIPT_DIR.glob("*.txt"))
    print(f"Found {len(transcript_files)} transcript files")
    
    for file_path in transcript_files:
        print(f"Processing transcript: {file_path.name}...")
        chunks = parse_transcript_chunks(file_path)
        documents.extend(chunks)
    
    print(f"Created {len(documents)} transcript chunks")
    return documents


def _extract_events_from_pdf_for_vectordb(pdf_path: str, page_index: int = 0):
    """
    Extract structured events from a single PDF page using Gemini,
    matching the logic from build_calendar_vectordb.py.
    """
    reader = PdfReader(pdf_path)
    page_text = reader.pages[page_index].extract_text() or ""

    client, model_name = _get_gemini_client()
    model = client.GenerativeModel(model_name)

    prompt = f"""
You are reading text extracted from page {page_index + 1} of a PDF. It contains a box listing events happening throughout a week.
These events are supposed to be community events or things happening in the neighborhood.
ONLY include events that are relevant to the community and also updates about other things.
From the text below, extract ALL events and their dates/times.

These events will also be stored as chunks in a vector database for semantic search.
Make each "raw_text" a short, self-contained snippet that clearly describes just that event.

Return ONLY valid JSON, no explanations, no backticks, in this exact shape:

IMPORTANT JSON RULES (follow strictly):
- Do NOT add any text before or after the JSON array.
- Do NOT add comments, headings, or Markdown.
- All strings must be valid JSON strings: escape newlines as \\n and quotes as \\".
- Do NOT include unescaped control characters inside strings.

The shape MUST be exactly:
[
  {{
    "event_name": "...",
    "event_date": "...",
    "start_date": "YYYY-MM-DD or null",
    "end_date": "YYYY-MM-DD or null",
    "start_time": "HH:MM or null",
    "end_time": "HH:MM or null",
    "raw_text": "..."
  }},
  ...
]

Field rules:
- "event_name": short human-readable name for the event.
- "event_date": the date or label exactly as written (e.g. "Monday", "June 3–5, 2025", "All week").
- "start_date": normalized calendar date when the event starts, in ISO format YYYY-MM-DD, or null if truly unknown.
- "end_date": normalized calendar date when the event ends, in ISO format YYYY-MM-DD, or null if same as start_date or unknown.
- "start_time": 24-hour time HH:MM when the event starts (e.g. "09:30"), or null if not specified.
- "end_time": 24-hour time HH:MM when the event ends, or null if not specified.
- "raw_text": the original line or snippet from the schedule describing this event.

Be conservative: never invent dates or times not clearly implied by the text. Use null when uncertain.

Text:
\"\"\"{page_text}\"\"\""""

    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0},
    )
    text = (getattr(response, "text", "") or "").strip()

    if text.startswith("```"):
        text = text.strip("`").strip()
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in ("json", "javascript", "js"):
            text = "\n".join(lines[1:]).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        safe_text = text.replace("\\", "\\\\")
        data = json.loads(safe_text)
    if not isinstance(data, list):
        return []

    events = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = (item.get("event_name") or "").strip()
        date = (item.get("event_date") or "").strip()
        start_date = (item.get("start_date") or "").strip() or None
        end_date = (item.get("end_date") or "").strip() or None
        start_time = (item.get("start_time") or "").strip() or None
        end_time = (item.get("end_time") or "").strip() or None
        raw = (item.get("raw_text") or "").strip()
        if not name or not date:
            continue
        events.append(
            {
                "event_name": name,
                "event_date": date,
                "start_date": start_date,
                "end_date": end_date,
                "start_time": start_time,
                "end_time": end_time,
                "raw_text": raw,
            }
        )
    return events


def _newsletter_events_to_documents(events, pdf_path: str):
    """Convert event dicts into Documents with doc_type=calendar_event."""
    pdf_name = Path(pdf_path).name
    documents = []

    for ev in events:
        raw_text = (ev.get("raw_text") or "").strip()
        if not raw_text:
            continue

        metadata = {
            "source": pdf_name,
            "doc_type": "calendar_event",
        }
        for key, value in ev.items():
            if key == "raw_text":
                continue
            metadata[key] = value

        documents.append(Document(page_content=raw_text, metadata=metadata))

    return documents


def load_newsletter_documents():
    """
    Load newsletter PDFs and convert extracted events into Documents,
    mirroring the chunking logic from build_calendar_vectordb.py.
    """
    documents = []

    if not NEWSLETTER_DIR.exists() or not NEWSLETTER_DIR.is_dir():
        return documents

    pdf_files = list(NEWSLETTER_DIR.glob("*.pdf"))
    print(f"Found {len(pdf_files)} newsletter PDFs")

    for pdf_path in pdf_files:
        reader = PdfReader(str(pdf_path))
        num_pages = len(reader.pages)
        all_events = []

        for page_index in range(num_pages):
            page_events = _extract_events_from_pdf_for_vectordb(
                str(pdf_path),
                page_index=page_index,
            )
            all_events.extend(page_events)

        docs = _newsletter_events_to_documents(all_events, str(pdf_path))
        documents.extend(docs)

    print(f"Created {len(documents)} newsletter calendar_event chunks")
    return documents


def build_vectordb():
    """
    Build or update the vector database from
    policy docs, meeting transcripts, and newsletters.
    """
    policy_docs = load_policy_documents()
    transcript_docs = load_transcript_documents()
    newsletter_docs = load_newsletter_documents()

    all_documents = policy_docs + transcript_docs + newsletter_docs

    if not all_documents:
        print("No documents found to add to vector DB.")
        return None

    print(f"\n{'='*80}")
    print(f"Total documents to add: {len(all_documents)}")
    print(f"  - Policy chunks: {len(policy_docs)}")
    print(f"  - Transcript chunks: {len(transcript_docs)}")
    print(f"  - Newsletter chunks: {len(newsletter_docs)}")
    print(f"{'='*80}\n")

    embeddings = GeminiEmbeddings()

    if VECTORDB_DIR.exists():
        print(f"Adding documents to existing vector database at {VECTORDB_DIR}")
        vectordb = Chroma(
            persist_directory=str(VECTORDB_DIR),
            embedding_function=embeddings,
        )
        vectordb.add_documents(all_documents)
    else:
        print(f"Creating new vector database at {VECTORDB_DIR}")
        vectordb = Chroma.from_documents(
            documents=all_documents,
            embedding=embeddings,
            persist_directory=str(VECTORDB_DIR),
        )

    print("Vector database update complete.")
    return vectordb


if __name__ == "__main__":
    build_vectordb()

