"""
ingest_rss.py  –  RSS feed ingestion for the Dorchester community chatbot.
 
Fetches entries from community RSS feeds, converts them to LangChain Documents,
deduplicates against the existing ChromaDB collection, and stores new entries.
 
Usage:
    python ingest_rss.py                  # ingest all feeds
    python ingest_rss.py --dry-run        # print what would be added, don't write
    python ingest_rss.py --reset          # wipe rss docs and re-ingest everything
 
Requires (add to requirements.txt if not present):
    feedparser
"""
 
from __future__ import annotations
 
import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
 
import feedparser
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
 
# ── path setup (mirrors ingest.py) ──────────────────────────────────────────
_THIS_FILE = Path(__file__).resolve()
_RAG_DIR   = _THIS_FILE.parent
_ROOT_DIR  = _RAG_DIR.parents[2]
load_dotenv()
 
if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))
 
from retrieval import GeminiEmbeddings  # noqa: E402  (same embeddings as the rest of the app)
 
# ── config ───────────────────────────────────────────────────────────────────
 
DEFAULT_VECTORDB_DIR = Path("../vectordb_new")
RSS_FEEDS: list[dict] = [
    {
        "url":    "https://www.dotnews.com/rss/",
        "source": "DOT Reporter",
        "tag":    "dorchester,news",
    },
    {
        "url":    "https://www.bpl.org/codman-square/feed/",
        "source": "Codman Square Library",
        "tag":    "codman square,library",
    },
    {
        "url":    "https://www.csndc.com/feed/",
        "source": "Codman Square Neighborhood Development Corporation",
        "tag":    "codman square,development",
    },
]
 
# ── helpers ───────────────────────────────────────────────────────────────────
 
def _stable_id(entry_id: str, source: str) -> str:
    """
    Deterministic short hash used as the ChromaDB document ID.
    Lets us skip entries we've already ingested on re-runs.
    """
    raw = f"{source}::{entry_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]
 
 
def _parse_date(entry) -> Optional[str]:
    """Return ISO-8601 date string from a feedparser entry, or None."""
    # feedparser populates published_parsed or updated_parsed as time.struct_time
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                dt = datetime(*t[:6], tzinfo=timezone.utc)
                return dt.date().isoformat()           # "YYYY-MM-DD"
            except Exception:
                pass
    return None
 
 
def _entry_to_document(entry, feed_meta: dict) -> Document:
    """Convert a single feedparser entry into a LangChain Document."""
    title   = getattr(entry, "title",   "").strip()
    summary = getattr(entry, "summary", "").strip()
    link    = getattr(entry, "link",    "").strip()
 
    # Build a self-contained text blob the LLM can use
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if summary:
        parts.append(f"Summary: {summary}")
    if link:
        parts.append(f"Link: {link}")
    page_content = "\n".join(parts) or title or "(no content)"
 
    pub_date = _parse_date(entry)
 
    metadata: dict = {
        "source":   feed_meta["source"],
        "doc_type": "calendar_event",          # keeps it consistent with newsletters
        "feed_url": feed_meta["url"],
        "link":     link,
        "tags":     feed_meta.get("tag", ""),
    }
    if pub_date:
        metadata["start_date"] = pub_date
 
    return Document(page_content=page_content, metadata=metadata)
 
 
# ── core pipeline ─────────────────────────────────────────────────────────────
 
def fetch_feed(feed_meta: dict) -> list[tuple[str, Document]]:
    """
    Fetch one RSS feed and return a list of (stable_id, Document) tuples.
    Prints a warning and returns [] on any network / parse failure.
    """
    url = feed_meta["url"]
    print(f"  Fetching {feed_meta['source']} ({url}) …", end=" ", flush=True)
 
    parsed = feedparser.parse(url)
 
    if parsed.get("bozo") and not parsed.entries:
        print(f"FAILED ({parsed.bozo_exception})")
        return []
 
    results = []
    for entry in parsed.entries:
        entry_id = getattr(entry, "id", None) or getattr(entry, "link", None) or ""
        if not entry_id:
            continue
        sid = _stable_id(entry_id, feed_meta["source"])
        doc = _entry_to_document(entry, feed_meta)
        results.append((sid, doc))
 
    print(f"OK  ({len(results)} entries)")
    return results
 
 
def ingest_rss(
    vectordb_dir: Path = DEFAULT_VECTORDB_DIR,
    feeds: list[dict] = RSS_FEEDS,
    dry_run: bool = False,
    reset: bool = False,
):
    """
    Main entry point.  Fetches all feeds, deduplicates, and upserts new docs.
    """
    print("\n" + "=" * 70)
    print("RSS Ingestion Pipeline")
    print("=" * 70)
 
    # ── fetch all feeds ───────────────────────────────────────────────────────
    all_items: list[tuple[str, Document]] = []
    for feed_meta in feeds:
        items = fetch_feed(feed_meta)
        all_items.extend(items)
 
    if not all_items:
        print("\nNo entries fetched from any feed.  Nothing to do.")
        return
 
    print(f"\nTotal entries fetched: {len(all_items)}")
 
    # ── open / create vectordb ────────────────────────────────────────────────
    embeddings = GeminiEmbeddings()
 
    if vectordb_dir.exists():
        vectordb = Chroma(
            persist_directory=str(vectordb_dir),
            embedding_function=embeddings,
        )
    else:
        print(f"Creating new vectordb at {vectordb_dir}")
        vectordb = Chroma(
            persist_directory=str(vectordb_dir),
            embedding_function=embeddings,
        )
 
    # ── optionally wipe existing rss docs ────────────────────────────────────
    if reset:
        print("--reset: removing existing RSS docs from vectordb …")
        existing = vectordb.get(where={"doc_type": "calendar_event"})
        rss_ids  = [
            id_ for id_, meta in zip(
                existing["ids"], existing["metadatas"]
            )
            if meta.get("feed_url")          # only RSS-sourced docs have feed_url
        ]
        if rss_ids:
            vectordb.delete(ids=rss_ids)
            print(f"  Deleted {len(rss_ids)} existing RSS docs.")
        else:
            print("  No existing RSS docs found.")
 
    # ── deduplicate against existing ids ─────────────────────────────────────
    existing_ids: set[str] = set(vectordb.get()["ids"])
    new_items = [(sid, doc) for sid, doc in all_items if sid not in existing_ids]
 
    print(f"Already in DB:  {len(all_items) - len(new_items)}")
    print(f"New to add:     {len(new_items)}")
 
    if not new_items:
        print("\nNothing new to ingest.  Done.")
        return
 
    if dry_run:
        print("\n-- DRY RUN: would add the following entries --")
        for sid, doc in new_items[:10]:
            print(f"  [{sid}] {doc.page_content[:80].replace(chr(10), ' ')} …")
        if len(new_items) > 10:
            print(f"  … and {len(new_items) - 10} more")
        return
 
    # ── upsert into ChromaDB ──────────────────────────────────────────────────
    ids  = [sid  for sid, _   in new_items]
    docs = [doc  for _,   doc in new_items]
 
    vectordb.add_documents(documents=docs, ids=ids)
 
    print(f"\n✓ Added {len(new_items)} new RSS entries to vectordb.")
    print(f"  DB location: {vectordb_dir.resolve()}")
    print("=" * 70 + "\n")
 
 
# ── CLI ───────────────────────────────────────────────────────────────────────
 
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest RSS feeds into ChromaDB")
    parser.add_argument(
        "--vectordb-dir",
        type=Path,
        default=DEFAULT_VECTORDB_DIR,
        help="Path to ChromaDB persist directory (default: ../vectordb_new)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse feeds but don't write to the database",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing RSS docs from the DB before re-ingesting",
    )
    args = parser.parse_args()
 
    ingest_rss(
        vectordb_dir=args.vectordb_dir,
        feeds=RSS_FEEDS,
        dry_run=args.dry_run,
        reset=args.reset,
    )
