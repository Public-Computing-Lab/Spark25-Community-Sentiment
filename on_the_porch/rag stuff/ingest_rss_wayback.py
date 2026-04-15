"""
ingest_rss_wayback.py  –  Backfill historical RSS snapshots via Wayback Machine CDX API.

For each feed in RSS_FEEDS, queries the Wayback CDX API for all archived snapshots
of that feed URL, fetches each snapshot, parses it with feedparser, and upserts
new entries into ChromaDB using the same deduplication logic as ingest_rss.py.

Usage:
    python ingest_rss_wayback.py                        # backfill all feeds
    python ingest_rss_wayback.py --dry-run              # print what would be added
    python ingest_rss_wayback.py --limit 10             # max 10 snapshots per feed
    python ingest_rss_wayback.py --from-date 20200101   # snapshots from date onward (YYYYMMDD)
    python ingest_rss_wayback.py --to-date 20231231     # snapshots up to date
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
import sys
from html.parser import HTMLParser
import re

import feedparser
import requests
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma

# ── path setup ───────────────────────────────────────────────────────────────
_THIS_FILE = Path(__file__).resolve()
_RAG_DIR   = _THIS_FILE.parent
load_dotenv()

if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))

from retrieval import GeminiEmbeddings  # noqa: E402
from ingest_rss import (               # reuse everything from ingest_rss.py
    RSS_FEEDS,
    DEFAULT_VECTORDB_DIR,
    _stable_id,
    _entry_to_document,
)

# ── config ────────────────────────────────────────────────────────────────────
CDX_API      = "http://web.archive.org/cdx/search/cdx"
WAYBACK_BASE = "https://web.archive.org/web"
REQUEST_DELAY = 1.5   # seconds between Wayback requests — be polite


# ── CDX helpers ───────────────────────────────────────────────────────────────

def get_snapshots(feed_url: str, from_date: str = "", to_date: str = "", limit: int = 0) -> list[str]:
    """
    Query CDX API for all archived snapshots of feed_url.
    Returns a list of timestamps (e.g. "20210304123456") sorted oldest-first.
    """
    params = {
        "url":      feed_url,
        "output":   "json",
        "fl":       "timestamp,statuscode",
        "filter":   "statuscode:200",   # only successful captures
        "collapse":  "timestamp:8",     # one snapshot per day max
    }
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if limit:
        params["limit"] = limit

    try:
        resp = requests.get(CDX_API, params=params, timeout=30)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        print(f"    CDX query failed for {feed_url}: {e}")
        return []

    # rows[0] is the header ["timestamp","statuscode"], skip it
    timestamps = [row[0] for row in rows[1:]]
    return timestamps


def fetch_wayback_feed(feed_url: str, timestamp: str, feed_meta: dict) -> list[tuple[str, object]]:
    """
    Fetch one archived snapshot of feed_url and parse it.
    Returns list of (stable_id, Document) tuples, same format as ingest_rss.fetch_feed.
    """
    url = f"{WAYBACK_BASE}/{timestamp}/{feed_url}"
    try:
        resp = requests.get(url, timeout=40)
        resp.raise_for_status()
    except Exception as e:
        print(f"      Snapshot {timestamp} fetch failed: {e}")
        return []

    parsed = feedparser.parse(resp.text)
    if not parsed.entries:
        return []

    results = []
    for entry in parsed.entries:
        entry_id = getattr(entry, "id", None) or getattr(entry, "link", None) or ""
        if not entry_id:
            continue
        sid = _stable_id(entry_id, feed_meta["source"])
        doc = _entry_to_document(entry, feed_meta)
        results.append((sid, doc))

    return results



# ── core pipeline ─────────────────────────────────────────────────────────────

def ingest_rss_wayback(
    vectordb_dir: Path = DEFAULT_VECTORDB_DIR,
    feeds: list[dict] = RSS_FEEDS,
    dry_run: bool = False,
    from_date: str = "",
    to_date: str = "",
    limit: int = 0,
):
    print("\n" + "=" * 70)
    print("Wayback Machine RSS Backfill Pipeline")
    print("=" * 70)

    embeddings = GeminiEmbeddings()
    vectordb   = Chroma(
        persist_directory=str(vectordb_dir),
        embedding_function=embeddings,
    )
    existing_ids: set[str] = set(vectordb.get()["ids"])

    all_new: list[tuple[str, object]] = []

    for feed_meta in feeds:
        feed_url = feed_meta["url"]
        print(f"\n[{feed_meta['source']}]  {feed_url}")

        timestamps = get_snapshots(feed_url, from_date=from_date, to_date=to_date, limit=limit)
        if not timestamps:
            print("  No snapshots found.")
            continue

        print(f"  {len(timestamps)} snapshots to process …")

        feed_new = 0
        for ts in timestamps:
            items = fetch_wayback_feed(feed_url, ts, feed_meta)
            new_items = [(sid, doc) for sid, doc in items if sid not in existing_ids]

            for sid, doc in new_items:
                existing_ids.add(sid)   # avoid adding same entry from two snapshots
                all_new.append((sid, doc))
                feed_new += 1

            time.sleep(REQUEST_DELAY)

        print(f"  → {feed_new} new entries from this feed's history")

    print(f"\nTotal new entries across all feeds: {len(all_new)}")

    if not all_new:
        print("Nothing new to ingest.  Done.")
        return

    if dry_run:
        print("\n-- DRY RUN: would add the following entries --")
        for sid, doc in all_new[:10]:
            print(f"  [{sid}] {doc.page_content[:80].replace(chr(10), ' ')} …")
        if len(all_new) > 10:
            print(f"  … and {len(all_new) - 10} more")
        return

    ids  = [sid for sid, _   in all_new]
    docs = [doc for _,   doc in all_new]
    vectordb.add_documents(documents=docs, ids=ids)

    print(f"\n✓ Added {len(all_new)} historical RSS entries to vectordb.")
    print(f"  DB location: {vectordb_dir.resolve()}")
    print("=" * 70 + "\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill historical RSS via Wayback Machine")
    parser.add_argument("--vectordb-dir", type=Path, default=DEFAULT_VECTORDB_DIR)
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--limit",        type=int, default=0,  help="Max snapshots per feed (0 = all)")
    parser.add_argument("--from-date",    default="",           help="Start date YYYYMMDD")
    parser.add_argument("--to-date",      default="",           help="End date YYYYMMDD")
    args = parser.parse_args()

    ingest_rss_wayback(
        vectordb_dir=args.vectordb_dir,
        dry_run=args.dry_run,
        from_date=args.from_date,
        to_date=args.to_date,
        limit=args.limit,
    )