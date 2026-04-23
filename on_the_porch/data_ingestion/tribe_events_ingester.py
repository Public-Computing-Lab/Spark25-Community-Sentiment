"""
Standalone ingester for any site running The Events Calendar WordPress plugin.

Currently supports:
  - csndc.com    (Codman Square NDC)
  - codman.org   (Codman Square Health Center)

Both sites expose a clean JSON REST API at
    <base>/wp-json/tribe/events/v1/events
so there's no PDF download, no pypdf, no Gemini call. Just paginated GETs,
normalize fields, and upsert into weekly_events — same schema as the dotnews
ingester.

Usage:
    python tribe_events_ingester.py csndc
    python tribe_events_ingester.py codman --all
    python tribe_events_ingester.py all --dry-run
    python tribe_events_ingester.py csndc --json saved.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import urlencode

import pymysql
import requests
from dotenv import load_dotenv

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent.parent
load_dotenv(REPO_ROOT / ".env")

# ---------------------------------------------------------------------------
# Source registry — add another line here if you want a third site.
# ---------------------------------------------------------------------------
SOURCES: dict[str, dict] = {
    "csndc": {
        "base_url": "https://www.csndc.com",
        "label": "csndc",
    },
    "codman": {
        "base_url": "https://www.codman.org",
        "label": "codman",
    },
}

PER_PAGE = 50
REQUEST_TIMEOUT = 30


# ---------------------------------------------------------------------------
# DB connection (same env vars as dotnews_ingester)
# ---------------------------------------------------------------------------
def get_db_connection():
    try:
        return pymysql.connect(
            host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
            port=int(os.environ.get("MYSQL_PORT", "3306")),
            user=os.environ.get("MYSQL_USER", "root"),
            password=os.environ.get("MYSQL_PASSWORD", ""),
            database=os.environ.get("MYSQL_DB", "sentiment_demo"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.Cursor,
            autocommit=True,
        )
    except Exception as exc:
        print(f"✗ MySQL connection failed: {exc}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------
def fetch_events(base_url: str, include_past: bool = False) -> list[dict]:
    """Page through a Tribe Events REST API and return all raw event dicts."""
    endpoint = f"{base_url.rstrip('/')}/wp-json/tribe/events/v1/events"
    all_events: list[dict] = []
    page = 1
    while True:
        params = {"page": page, "per_page": PER_PAGE}
        if include_past:
            params["start_date"] = "2000-01-01 00:00:00"
            params["status"] = "publish"
        url = f"{endpoint}?{urlencode(params)}"
        print(f"  ↪ GET {url}")
        try:
            r = requests.get(url, timeout=REQUEST_TIMEOUT)
        except Exception as e:
            print(f"  ✗ Network error: {e}")
            break

        # Tribe returns 404 when you page past the last page — this is normal.
        if r.status_code == 404:
            print("  ↪ End of results (404)")
            break
        if r.status_code != 200:
            print(f"  ✗ HTTP {r.status_code}: {r.text[:200]}")
            break

        try:
            data = r.json()
        except ValueError:
            print("  ✗ Response was not JSON")
            break

        events = data.get("events") or []
        if not events:
            print("  ↪ No more events on this page")
            break

        print(f"   + {len(events)} events on page {page}")
        all_events.extend(events)

        if len(events) < PER_PAGE:
            break
        page += 1

    return all_events


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    cleaned = _TAG_RE.sub(" ", text)
    cleaned = unescape(cleaned)
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    return cleaned


def split_datetime(dt_str: str | None) -> tuple[str | None, str | None]:
    """Split 'YYYY-MM-DD HH:MM:SS' into (date, HH:MM) or (None, None)."""
    if not dt_str:
        return None, None
    s = str(dt_str).strip().replace("T", " ")
    if not s:
        return None, None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[ ](\d{2}:\d{2})(?::\d{2})?)?", s)
    if not m:
        return None, None
    date_part, time_part = m.group(1), m.group(2)
    try:
        datetime.strptime(date_part, "%Y-%m-%d")
    except ValueError:
        return None, None
    return date_part, time_part


def pick_category(raw_event: dict) -> str:
    """Keyword-based category mapping — works for both CSNDC and Codman events."""
    tribe_cats = raw_event.get("categories") or []
    names = [c.get("name", "") for c in tribe_cats if isinstance(c, dict)]
    joined = " ".join(names).lower()
    title = (raw_event.get("title") or "").lower()
    desc = strip_html(raw_event.get("description") or "").lower()
    blob = f"{joined} {title} {desc}"

    if any(k in blob for k in ("prenatal", "baby", "maternity", "youth", "family",
                               "kid", "teen", "pediatric", "parent", "infant")):
        return "Youth/Family"
    if any(k in blob for k in ("meeting", "public", "hearing", "forum",
                               "town hall", "community meeting")):
        return "Public Meeting"
    if any(k in blob for k in ("art", "music", "culture", "expo", "festival", "jerkfest")):
        return "Arts/Culture"
    if any(k in blob for k in ("health", "wellness", "clinic", "recovery", "substance",
                               "prep", "hiv", "nutrition", "fitness", "mental")):
        return "Health/Wellness"
    if any(k in blob for k in ("housing", "homebuyer", "tenant", "rent", "foreclosure")):
        return "Housing"
    if any(k in blob for k in ("safety", "police", "night out")):
        return "Safety"
    if any(k in blob for k in ("education", "workshop", "class", "training", "course")):
        return "Education"
    return "Other"


def normalize_event(raw: dict, source_label: str) -> dict | None:
    """Map a Tribe REST event dict to the weekly_events row shape."""
    title = strip_html(raw.get("title")) or ""
    if not title:
        return None

    start_date, start_time = split_datetime(raw.get("start_date"))
    end_date, end_time = split_datetime(raw.get("end_date"))

    if start_date and end_date and start_date != end_date:
        event_date = f"{start_date} to {end_date}"
    elif start_date:
        event_date = start_date
    else:
        event_date = "no info"

    # Location: prefer venue name + address if the site fills those in.
    location = None
    venue = raw.get("venue")
    if isinstance(venue, dict):
        parts = [
            venue.get("venue"),
            venue.get("address"),
            venue.get("city"),
            venue.get("state_province") or venue.get("state"),
        ]
        location = ", ".join(p for p in parts if p) or None

    description = strip_html(raw.get("description")) or strip_html(raw.get("excerpt"))
    raw_text_parts = [title]
    if description:
        raw_text_parts.append(description)
    if location:
        raw_text_parts.append(f"Location: {location}")
    if raw.get("url"):
        raw_text_parts.append(f"URL: {raw['url']}")
    raw_text = "\n".join(raw_text_parts)[:5000]

    return {
        "event_name": title[:255],
        "event_date": event_date,
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
        "raw_text": raw_text,
        "location": location,
        "category": pick_category(raw),
        "source": source_label,
    }


# ---------------------------------------------------------------------------
# DB insert
# ---------------------------------------------------------------------------
def insert_events_to_db(events: list[dict]) -> int:
    if not events:
        return 0

    conn = get_db_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            # Make sure category column exists (same pattern as dotnews ingester).
            cur.execute("SHOW COLUMNS FROM weekly_events LIKE 'category'")
            if not cur.fetchone():
                try:
                    cur.execute("ALTER TABLE weekly_events ADD COLUMN category TEXT")
                    print("  ℹ Added 'category' column to weekly_events")
                except Exception as e:
                    print(f"  ⚠ Could not add category column: {e}")

            for event in events:
                event_name = event.get("event_name") or ""
                if not event_name:
                    continue

                # Dedupe on (source, event_name, start_date) — important for
                # Codman because recurring events (e.g. Virtual Baby Cafe every
                # Wednesday) each have their own occurrence row we want to keep,
                # but reruns shouldn't duplicate them.
                try:
                    cur.execute(
                        """
                        SELECT id FROM weekly_events
                        WHERE source_pdf = %s AND event_name = %s
                          AND (start_date <=> %s)
                        LIMIT 1
                        """,
                        (event.get("source"), event_name, event.get("start_date")),
                    )
                    if cur.fetchone():
                        continue
                except Exception:
                    # If the schema doesn't allow this query, fall through and
                    # let the insert run (or a unique index error harmlessly).
                    pass

                try:
                    cur.execute(
                        """
                        INSERT INTO weekly_events (
                            source_pdf, page_number, event_name, event_date,
                            start_date, end_date, start_time, end_time,
                            raw_text, category
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            event.get("source"),
                            None,  # no page_number for API-sourced events
                            event_name,
                            event.get("event_date"),
                            event.get("start_date"),
                            event.get("end_date"),
                            event.get("start_time"),
                            event.get("end_time"),
                            event.get("raw_text", ""),
                            event.get("category", "Other"),
                        ),
                    )
                    inserted += 1
                except Exception as e:
                    print(f"    ⚠ Could not insert '{event_name}': {e}")
    finally:
        conn.close()
    return inserted


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_source(source_key: str, include_past: bool, dry_run: bool,
               json_path: Path | None = None) -> int:
    cfg = SOURCES[source_key]
    label = cfg["label"]
    print(f"\n=== Ingesting {source_key} ({cfg['base_url']}) ===")

    if json_path:
        if not json_path.exists():
            print(f"✗ JSON file not found: {json_path}", file=sys.stderr)
            return 0
        print(f"📄 Loading events from {json_path}")
        data = json.loads(json_path.read_text())
        raw_events = data.get("events", data) if isinstance(data, dict) else data
    else:
        print("🌐 Fetching events from The Events Calendar API...")
        raw_events = fetch_events(cfg["base_url"], include_past=include_past)

    print(f"📥 Fetched {len(raw_events)} raw events from {source_key}")

    normalized = []
    for raw in raw_events:
        norm = normalize_event(raw, source_label=label)
        if norm:
            normalized.append(norm)
    print(f"✅ Normalized {len(normalized)} events")

    if dry_run:
        print(f"\n--- DRY RUN: first 3 normalized events from {source_key} ---")
        for ev in normalized[:3]:
            print(json.dumps(ev, indent=2, default=str))
        return 0

    if not normalized:
        print("⚠ No events to insert")
        return 0

    inserted = insert_events_to_db(normalized)
    print(f"✓ Inserted {inserted} events into weekly_events (source={label})")
    skipped = len(normalized) - inserted
    if skipped > 0:
        print(f"  (skipped {skipped} already-present events)")
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest events from Tribe-powered sites.")
    parser.add_argument(
        "source",
        choices=list(SOURCES.keys()) + ["all"],
        help="Which source to ingest (csndc, codman, or 'all')",
    )
    parser.add_argument("--all", dest="include_past", action="store_true",
                        help="Include past events (default: only upcoming)")
    parser.add_argument("--json", type=Path, default=None,
                        help="Load raw events from a local JSON file instead of fetching")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch + normalize but don't write to the database")
    args = parser.parse_args()

    sources_to_run = list(SOURCES.keys()) if args.source == "all" else [args.source]

    if args.json and len(sources_to_run) > 1:
        print("✗ --json can only be used with a single source", file=sys.stderr)
        return 1

    total = 0
    for src in sources_to_run:
        total += run_source(src, args.include_past, args.dry_run, json_path=args.json)

    if not args.dry_run:
        print(f"\n🎉 Grand total inserted: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())