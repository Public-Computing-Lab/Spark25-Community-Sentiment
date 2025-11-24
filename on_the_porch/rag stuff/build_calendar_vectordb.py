from pathlib import Path
import os
import json

from pypdf import PdfReader
import google.generativeai as genai  # type: ignore
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from dotenv import load_dotenv


load_dotenv()
CALENDAR_PDF_DIR = Path("B:/BOSTON UNI/Acad/ML Spark/ml-misi-community-sentiment/on_the_porch/rag stuff/Data/newsletters")
CALENDAR_VECTORDB_DIR = Path("../vectordb_calendar")


def _get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    genai.configure(api_key=api_key)
    return genai, model_name


def _extract_events_from_pdf_for_vectordb(pdf_path: str, page_index: int = 0):
    """
    Use Gemini to turn text from one PDF page into structured events
    for storage in the calendar vector database.
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

    # Strip accidental code fences if the model adds them
    if text.startswith("```"):
        text = text.strip("`").strip()
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in ("json", "javascript", "js"):
            text = "\n".join(lines[1:]).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Crude fallback: escape backslashes to handle invalid \-escapes from the model
        safe_text = text.replace("\\", "\\\\")
        data = json.loads(safe_text)
    if not isinstance(data, list):
        raise RuntimeError(f"Gemini JSON is not a list: {data!r}")

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


def events_to_documents(events, pdf_path: str):
    """Convert event dicts into LangChain Documents for the calendar vector DB."""
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


def load_calendar_documents():
    """Load calendar PDFs and convert extracted events into Documents."""
    documents = []

    if not CALENDAR_PDF_DIR.exists() or not CALENDAR_PDF_DIR.is_dir():
        raise RuntimeError(f"Calendar PDF directory not found or not a directory: {CALENDAR_PDF_DIR}")

    pdf_files = list(CALENDAR_PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        raise RuntimeError(f"No PDF files found in calendar directory: {CALENDAR_PDF_DIR}")

    for pdf_path in pdf_files:
        reader = PdfReader(str(pdf_path))
        num_pages = len(reader.pages)
        all_events = []
        for page_index in range(num_pages):
            page_events = _extract_events_from_pdf_for_vectordb(str(pdf_path), page_index=page_index)
            all_events.extend(page_events)
        documents.extend(events_to_documents(all_events, str(pdf_path)))

    return documents


def build_calendar_vectordb():
    """Build a separate vector database from calendar event PDFs."""
    calendar_docs = load_calendar_documents()

    print(f"\n{'='*80}")
    print(f"Calendar documents: {len(calendar_docs)}")
    print(f"{'='*80}\n")

    embeddings = OpenAIEmbeddings()

    if CALENDAR_VECTORDB_DIR.exists():
        print(f"Removing existing calendar vector database at {CALENDAR_VECTORDB_DIR}")
        import shutil
        shutil.rmtree(CALENDAR_VECTORDB_DIR)

    print(f"Building calendar vector database at {CALENDAR_VECTORDB_DIR}")
    vectordb = Chroma.from_documents(
        documents=calendar_docs,
        embedding=embeddings,
        persist_directory=str(CALENDAR_VECTORDB_DIR),
    )

    print("Calendar vector database built successfully!")
    return vectordb


if __name__ == "__main__":
    build_calendar_vectordb()


