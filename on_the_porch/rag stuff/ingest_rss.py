"""
RSS ingestion for the Dorchester community chatbot.

Fetches entries from community RSS feeds, converts them to LangChain Documents,
deduplicates against the existing Chroma collection, and stores new entries.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import feedparser
from dotenv import load_dotenv
from langchain_core.documents import Document

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma

_THIS_FILE = Path(__file__).resolve()
_RAG_DIR = _THIS_FILE.parent
_ROOT_DIR = _RAG_DIR.parents[2]
load_dotenv(_ROOT_DIR / ".env")

if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))

from retrieval import GeminiEmbeddings  # noqa: E402

DEFAULT_VECTORDB_DIR = Path("../vectordb_new")
RSS_FEEDS: list[dict[str, str]] = [
    {
        "url": "https://www.dotnews.com/rss/",
        "source": "DOT Reporter",
        "tag": "dorchester,news",
    },
    {
        "url": "https://www.bpl.org/codman-square/feed/",
        "source": "Codman Square Library",
        "tag": "codman square,library",
    },
    {
        "url": "https://www.csndc.com/feed/",
        "source": "Codman Square Neighborhood Development Corporation",
        "tag": "codman square,development",
    },
]


def _stable_id(entry_id: str, source: str) -> str:
    raw = f"{source}::{entry_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _parse_date(entry) -> Optional[str]:
    for attr in ("published_parsed", "updated_parsed"):
        parsed_time = getattr(entry, attr, None)
        if not parsed_time:
            continue
        try:
            parsed_dt = datetime(*parsed_time[:6], tzinfo=timezone.utc)
            return parsed_dt.date().isoformat()
        except Exception:
            continue
    return None


def _entry_to_document(entry, feed_meta: dict[str, str]) -> Document:
    title = getattr(entry, "title", "").strip()
    summary = getattr(entry, "summary", "").strip()
    link = getattr(entry, "link", "").strip()

    parts = []
    if title:
        parts.append(f"Title: {title}")
    if summary:
        parts.append(f"Summary: {summary}")
    if link:
        parts.append(f"Link: {link}")
    page_content = "\n".join(parts) or title or "(no content)"

    metadata = {
        "source": feed_meta["source"],
        "doc_type": "calendar_event",
        "feed_url": feed_meta["url"],
        "link": link,
        "tags": feed_meta.get("tag", ""),
    }
    published_date = _parse_date(entry)
    if published_date:
        metadata["start_date"] = published_date

    return Document(page_content=page_content, metadata=metadata)


def fetch_feed(feed_meta: dict[str, str]) -> list[tuple[str, Document]]:
    url = feed_meta["url"]
    print(f"  Fetching {feed_meta['source']} ({url}) ...", end=" ", flush=True)
    parsed = feedparser.parse(url)

    if parsed.get("bozo") and not parsed.entries:
        print(f"FAILED ({parsed.bozo_exception})")
        return []

    items: list[tuple[str, Document]] = []
    for entry in parsed.entries:
        entry_id = getattr(entry, "id", None) or getattr(entry, "link", None) or ""
        if not entry_id:
            continue
        items.append((_stable_id(entry_id, feed_meta["source"]), _entry_to_document(entry, feed_meta)))

    print(f"OK ({len(items)} entries)")
    return items


def ingest_rss(
    vectordb_dir: Path = DEFAULT_VECTORDB_DIR,
    feeds: list[dict[str, str]] = RSS_FEEDS,
    dry_run: bool = False,
    reset: bool = False,
) -> None:
    print("\n" + "=" * 70)
    print("RSS Ingestion Pipeline")
    print("=" * 70)

    all_items: list[tuple[str, Document]] = []
    for feed_meta in feeds:
        all_items.extend(fetch_feed(feed_meta))

    if not all_items:
        print("\nNo entries fetched from any feed. Nothing to do.")
        return

    embeddings = GeminiEmbeddings()
    vectordb = Chroma(
        persist_directory=str(vectordb_dir),
        embedding_function=embeddings,
    )

    if reset:
        print("--reset: removing existing RSS docs from vectordb ...")
        existing = vectordb.get(where={"doc_type": "calendar_event"})
        rss_ids = [
            item_id
            for item_id, metadata in zip(existing.get("ids", []), existing.get("metadatas", []))
            if (metadata or {}).get("feed_url")
        ]
        if rss_ids:
            vectordb.delete(ids=rss_ids)
            print(f"  Deleted {len(rss_ids)} existing RSS docs.")
        else:
            print("  No existing RSS docs found.")

    existing_ids = set(vectordb.get().get("ids", []))
    new_items = [(item_id, doc) for item_id, doc in all_items if item_id not in existing_ids]

    print(f"Already in DB: {len(all_items) - len(new_items)}")
    print(f"New to add:    {len(new_items)}")

    if not new_items:
        print("\nNothing new to ingest. Done.")
        return

    if dry_run:
        print("\n-- DRY RUN: would add the following entries --")
        for item_id, doc in new_items[:10]:
            preview = doc.page_content[:80].replace("\n", " ")
            print(f"  [{item_id}] {preview} ...")
        if len(new_items) > 10:
            print(f"  ... and {len(new_items) - 10} more")
        return

    vectordb.add_documents(
        documents=[doc for _, doc in new_items],
        ids=[item_id for item_id, _ in new_items],
    )

    print(f"\nAdded {len(new_items)} new RSS entries to vectordb.")
    print(f"DB location: {vectordb_dir.resolve()}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest RSS feeds into ChromaDB")
    parser.add_argument(
        "--vectordb-dir",
        type=Path,
        default=DEFAULT_VECTORDB_DIR,
        help="Path to ChromaDB persist directory (default: ../vectordb_new)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse feeds but do not write to the database")
    parser.add_argument("--reset", action="store_true", help="Delete existing RSS docs before re-ingesting")
    args = parser.parse_args()

    ingest_rss(vectordb_dir=args.vectordb_dir, feeds=RSS_FEEDS, dry_run=args.dry_run, reset=args.reset)
