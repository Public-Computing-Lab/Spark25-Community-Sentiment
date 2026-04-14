"""
ingest_311_911_to_rag.py

Parses Boston 311 service request and crime incident (911) data from MySQL,
converts records into rich semantic text chunks, embeds them into the ChromaDB
vector store (RAG), and tracks ingestion state in a dedicated MySQL table to
avoid re-embedding the same records on subsequent runs.

Usage:
    python ingest_311_911_to_rag.py                  # last 30 days, both sources
    python ingest_311_911_to_rag.py --days 7         # last 7 days
    python ingest_311_911_to_rag.py --source 311     # 311 only
    python ingest_311_911_to_rag.py --source crime   # crime only
    python ingest_311_911_to_rag.py --aggregate      # aggregate summaries only
    python ingest_311_911_to_rag.py --batch-size 200 # records per embedding batch

Can also be imported and called from main_daily_ingestion.py:
    from ingest_311_911_to_rag import run_ingestion
    stats = run_ingestion(days=30)
"""

import os
import sys
import json
import argparse
import hashlib
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path setup — mirror the pattern used throughout this project
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_INGEST_DIR = _THIS_FILE.parent
_ROOT_DIR = _INGEST_DIR.parents[2]
_ON_THE_PORCH_DIR = _ROOT_DIR / "on_the_porch"
_RAG_STUFF_DIR = _ON_THE_PORCH_DIR / "rag stuff"

load_dotenv(_ROOT_DIR / ".env")

# Add rag stuff to path so we can import GeminiEmbeddings and Chroma helpers
if str(_RAG_STUFF_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_STUFF_DIR))

from retrieval import GeminiEmbeddings  # noqa: E402  (after path setup)

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma  # type: ignore

from langchain_core.documents import Document  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default ChromaDB path (same DB used by the chatbot)
DEFAULT_VECTORDB_DIR = _ON_THE_PORCH_DIR / "vectordb_new"

# MySQL connection — reads from env, matching api_v2.py and boston_data_sync.py
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DB", "rethink_ai_boston"),
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
}

# Table that tracks which record IDs have already been embedded
RAG_TRACKING_TABLE = "rag_ingestion_log"

# Batch size when calling ChromaDB .add_documents() — keeps Gemini API happy
DEFAULT_BATCH_SIZE = 100

# Columns to pull from each table (avoids fetching large unused fields)
COLS_311 = [
    "case_id", "case_enquiry_id", "open_dt", "closed_dt",
    "case_status", "closure_reason", "case_title",
    "subject", "reason", "type", "neighborhood",
    "street", "latitude", "longitude",
]

COLS_CRIME = [
    "incident_number", "offense_code", "offense_code_group",
    "offense_description", "district", "reporting_area",
    "shooting", "occurred_on_date", "year", "month",
    "day_of_week", "hour", "ucr_part", "street",
    "lat", "long",
]


# ---------------------------------------------------------------------------
# MySQL helpers
# ---------------------------------------------------------------------------

def _connect() -> pymysql.connections.Connection:
    """Open a pymysql connection using environment-configured credentials."""
    return pymysql.connect(**MYSQL_CONFIG)


def ensure_tracking_table(conn: pymysql.connections.Connection) -> None:
    """Create rag_ingestion_log if it doesn't exist yet."""
    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {RAG_TRACKING_TABLE} (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                source_type VARCHAR(50)  NOT NULL COMMENT '311_request or crime_incident',
                record_id   VARCHAR(255) NOT NULL COMMENT 'case_id or incident_number',
                chunk_id    VARCHAR(64)  NOT NULL COMMENT 'SHA-256 of the embedded text',
                ingested_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_record (source_type, record_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    conn.commit()
    print(f"  ✓ Tracking table '{RAG_TRACKING_TABLE}' ready")


def get_already_ingested_ids(
    conn: pymysql.connections.Connection, source_type: str
) -> set:
    """Return the set of record_ids already in the tracking table."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT record_id FROM {RAG_TRACKING_TABLE} WHERE source_type = %s",
            (source_type,),
        )
        rows = cur.fetchall()
    return {r["record_id"] for r in rows}


def mark_ingested(
    conn: pymysql.connections.Connection,
    source_type: str,
    records: List[Tuple[str, str]],  
) -> int:
    if not records:
        return 0
    with conn.cursor() as cursor:
        cursor.executemany(
            f"""
            INSERT IGNORE INTO {RAG_TRACKING_TABLE} (source_type, record_id, chunk_id)
            VALUES (%s, %s, %s)
            """,
            [(source_type, record_id, chunk_id) for record_id, chunk_id in records],
        )
    conn.commit()
    return len(records)


# ---------------------------------------------------------------------------
# 311 data — fetch + document building
# ---------------------------------------------------------------------------

def fetch_311_records(
    conn: pymysql.connections.Connection,
    days: int = 30,
    already_ingested: Optional[set] = None,
    limit: int = 5000,
) -> List[Dict[str, Any]]:
    """
    Pull 311 service requests opened within the last `days` days from MySQL.
    Skips records whose case_id is already in `already_ingested`.
    """
    since = datetime.now() - timedelta(days=days)
    cols = ", ".join(COLS_311)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {cols}
            FROM bos311_data
            WHERE open_dt >= %s
            ORDER BY open_dt DESC
            LIMIT %s
            """,
            (since.strftime("%Y-%m-%d %H:%M:%S"), limit),
        )
        rows = cur.fetchall()

    if already_ingested:
        rows = [r for r in rows if str(r.get("case_id") or r.get("case_enquiry_id", "")) not in already_ingested]

    return rows


def _311_record_to_text(r: Dict[str, Any]) -> str:
    """Convert a single 311 row into a descriptive natural-language sentence."""
    case_id = r.get("case_id") or r.get("case_enquiry_id", "unknown")
    title = r.get("case_title") or "Service Request"
    neighborhood = r.get("neighborhood") or "unknown neighborhood"
    street = r.get("street") or ""
    subject = r.get("subject") or ""
    reason = r.get("reason") or ""
    request_type = r.get("type") or ""
    status = r.get("case_status") or "Unknown"
    open_dt = r.get("open_dt")
    closed_dt = r.get("closed_dt")
    closure_reason = r.get("closure_reason") or ""

    open_str = str(open_dt)[:10] if open_dt else "unknown date"
    closed_str = str(closed_dt)[:10] if closed_dt else None

    location_str = f"{street}, {neighborhood}".strip(", ") if street else neighborhood

    lines = [
        f"311 Service Request #{case_id}: {title}.",
        f"Location: {location_str}.",
    ]

    if subject or reason or request_type:
        category_parts = [p for p in [subject, reason, request_type] if p]
        lines.append(f"Category: {' > '.join(category_parts)}.")

    lines.append(f"Reported: {open_str}. Status: {status}.")

    if closed_str:
        lines.append(f"Closed: {closed_str}.")

    if closure_reason:
        lines.append(f"Closure reason: {closure_reason}.")

    return " ".join(lines)


def build_311_documents(
    records: List[Dict[str, Any]],
) -> Tuple[List[Document], List[Tuple[str, str]]]:
    """
    Convert 311 rows into LangChain Documents with metadata.
    Returns (documents, [(record_id, chunk_id), ...]) for tracking.
    """
    documents = []
    tracking = []

    for r in records:
        record_id = str(r.get("case_id") or r.get("case_enquiry_id", ""))
        if not record_id:
            continue

        text = _311_record_to_text(r)
        chunk_id = hashlib.sha256(text.encode()).hexdigest()[:16]

        open_dt = r.get("open_dt")
        open_date_str = str(open_dt)[:10] if open_dt else ""

        metadata = {
            "doc_type": "311_request",
            "source": "Boston 311 Service Requests",
            "record_id": record_id,
            "case_title": r.get("case_title") or "",
            "neighborhood": r.get("neighborhood") or "",
            "case_status": r.get("case_status") or "",
            "open_date": open_date_str,
        }

        # Optional geo metadata (ChromaDB stores as string)
        lat = r.get("latitude")
        lng = r.get("longitude")
        if lat and lng:
            try:
                metadata["lat"] = str(float(lat))
                metadata["lng"] = str(float(lng))
            except (ValueError, TypeError):
                pass
        documents.append(Document(page_content=text, metadata=metadata))
        tracking.append((record_id, chunk_id))

    return documents, tracking


# ---------------------------------------------------------------------------
# 311 aggregate summaries (neighborhood × issue type × time window)
# ---------------------------------------------------------------------------

def build_311_aggregate_docs(
    records: List[Dict[str, Any]], window_label: str = "recent"
) -> List[Document]:
    """
    Group 311 records by (neighborhood, case_title) and produce one summary
    Document per group. Useful for semantic questions like
    "What are the main 311 issues in Dorchester?".
    """
    from collections import defaultdict

    groups: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for r in records:
        neighborhood = (r.get("neighborhood") or "Unknown Neighborhood").strip()
        title = (r.get("case_title") or "General Request").strip()
        groups[(neighborhood, title)].append(r)

    documents = []
    for (neighborhood, title), group_records in groups.items():
        count = len(group_records)
        statuses = [r.get("case_status") or "Unknown" for r in group_records]
        open_count = statuses.count("Open")
        closed_count = statuses.count("Closed")

        dates = []
        for r in group_records:
            od = r.get("open_dt")
            if od:
                dates.append(str(od)[:10])
        dates_sorted = sorted(set(dates))
        date_range = f"{dates_sorted[0]} to {dates_sorted[-1]}" if len(dates_sorted) > 1 else (dates_sorted[0] if dates_sorted else "unknown")

        text = (
            f"311 Summary for {neighborhood} — {title} ({window_label}): "
            f"{count} service request(s) reported between {date_range}. "
            f"{open_count} open, {closed_count} resolved."
        )

        # Sample closure reasons
        reasons = list({r.get("closure_reason") for r in group_records if r.get("closure_reason")})[:3]
        if reasons:
            text += f" Common closure reasons: {'; '.join(reasons)}."

        chunk_id = f"agg_311_{hashlib.sha256((neighborhood + title + window_label).encode()).hexdigest()[:12]}"

        documents.append(Document(
            page_content=text,
            metadata={
                "doc_type": "311_aggregate",
                "source": "Boston 311 Service Requests",
                "neighborhood": neighborhood,
                "case_title": title,
                "record_count": str(count),
                "window": window_label,
                "chunk_id": chunk_id,
            },
        ))

    return documents


# ---------------------------------------------------------------------------
# Crime / 911 data — fetch + document building
# ---------------------------------------------------------------------------

def fetch_crime_records(
    conn: pymysql.connections.Connection,
    days: int = 30,
    already_ingested: Optional[set] = None,
    limit: int = 5000,
) -> List[Dict[str, Any]]:
    """
    Pull crime incident records from the last `days` days from MySQL.
    Skips records whose incident_number is already tracked.
    """
    since = datetime.now() - timedelta(days=days)
    cols = ", ".join(COLS_CRIME)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {cols}
            FROM crime_incident_reports
            WHERE occurred_on_date >= %s
            ORDER BY occurred_on_date DESC
            LIMIT %s
            """,
            (since.strftime("%Y-%m-%d %H:%M:%S"), limit),
        )
        rows = cur.fetchall()

    if already_ingested:
        rows = [r for r in rows if str(r.get("incident_number", "")) not in already_ingested]

    return rows


def _crime_record_to_text(r: Dict[str, Any]) -> str:
    """Convert a single crime incident row into a descriptive sentence."""
    incident_num = r.get("incident_number", "unknown")
    offense = r.get("offense_description") or r.get("offense_code_group") or "Unknown Offense"
    district = r.get("district") or "unknown district"
    street = r.get("street") or ""
    occurred = r.get("occurred_on_date")
    day_of_week = r.get("day_of_week") or ""
    hour = r.get("hour")
    shooting = r.get("shooting")
    ucr_part = r.get("ucr_part") or ""

    occurred_str = str(occurred)[:10] if occurred else "unknown date"
    time_str = ""
    if hour is not None:
        try:
            h = int(hour)
            period = "AM" if h < 12 else "PM"
            h12 = h % 12 or 12
            time_str = f" at {h12}:00 {period}"
        except (ValueError, TypeError):
            pass

    location_str = f"{street}, District {district}".strip(", ") if street else f"District {district}"

    lines = [f"Crime Incident #{incident_num}: {offense}."]
    lines.append(f"Location: {location_str}.")
    lines.append(f"Occurred: {day_of_week} {occurred_str}{time_str}.")

    if shooting and str(shooting).strip().upper() in ("Y", "1", "TRUE"):
        lines.append("Shooting involved: Yes.")

    if ucr_part:
        lines.append(f"UCR Part: {ucr_part}.")

    return " ".join(lines)


def build_crime_documents(
    records: List[Dict[str, Any]],
) -> Tuple[List[Document], List[Tuple[str, str]]]:
    """
    Convert crime incident rows into LangChain Documents with metadata.
    Returns (documents, [(record_id, chunk_id), ...]) for tracking.
    """
    documents = []
    tracking = []

    for r in records:
        record_id = str(r.get("incident_number", ""))
        if not record_id:
            continue

        text = _crime_record_to_text(r)
        chunk_id = hashlib.sha256(text.encode()).hexdigest()[:16]

        occurred = r.get("occurred_on_date")
        occurred_str = str(occurred)[:10] if occurred else ""

        metadata = {
            "doc_type": "crime_incident",
            "source": "Boston Crime Incident Reports",
            "record_id": record_id,
            "offense_description": r.get("offense_description") or "",
            "offense_code_group": r.get("offense_code_group") or "",
            "district": r.get("district") or "",
            "occurred_date": occurred_str,
            "shooting": str(r.get("shooting") or ""),
        }

        lat = r.get("lat")
        lng = r.get("long")
        if lat and lng:
            try:
                metadata["lat"] = str(float(lat))
                metadata["lng"] = str(float(lng))
            except (ValueError, TypeError):
                pass
        documents.append(Document(page_content=text, metadata=metadata))
        tracking.append((record_id, chunk_id))

    return documents, tracking


# ---------------------------------------------------------------------------
# Crime aggregate summaries (district × offense group × time window)
# ---------------------------------------------------------------------------

def build_crime_aggregate_docs(
    records: List[Dict[str, Any]], window_label: str = "recent"
) -> List[Document]:
    """
    Group crime records by (district, offense_code_group) and produce one
    summary Document per group. Useful for questions like
    "What types of crimes happen in District B2?".
    """
    from collections import defaultdict

    groups: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for r in records:
        district = (r.get("district") or "Unknown District").strip()
        group_name = (r.get("offense_code_group") or "Other").strip()
        groups[(district, group_name)].append(r)

    documents = []
    for (district, group_name), group_records in groups.items():
        count = len(group_records)
        dates = []
        for r in group_records:
            od = r.get("occurred_on_date")
            if od:
                dates.append(str(od)[:10])
        dates_sorted = sorted(set(dates))
        date_range = f"{dates_sorted[0]} to {dates_sorted[-1]}" if len(dates_sorted) > 1 else (dates_sorted[0] if dates_sorted else "unknown")

        # Specific offenses breakdown
        offense_counts: Dict[str, int] = {}
        for r in group_records:
            od = r.get("offense_description") or "Other"
            offense_counts[od] = offense_counts.get(od, 0) + 1
        top_offenses = sorted(offense_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        offense_str = ", ".join(f"{o} ({c})" for o, c in top_offenses)

        shootings = sum(1 for r in group_records if str(r.get("shooting") or "").upper() in ("Y", "1", "TRUE"))

        text = (
            f"Crime Summary for District {district} — {group_name} ({window_label}): "
            f"{count} incident(s) between {date_range}."
        )
        if offense_str:
            text += f" Top offenses: {offense_str}."
        if shootings:
            text += f" Shooting incidents: {shootings}."

        chunk_id = f"agg_crime_{hashlib.sha256((district + group_name + window_label).encode()).hexdigest()[:12]}"

        documents.append(Document(
            page_content=text,
            metadata={
                "doc_type": "crime_aggregate",
                "source": "Boston Crime Incident Reports",
                "district": district,
                "offense_code_group": group_name,
                "record_count": str(count),
                "window": window_label,
                "chunk_id": chunk_id,
            },
        ))

    return documents


# ---------------------------------------------------------------------------
# ChromaDB helpers
# ---------------------------------------------------------------------------

def _get_vectordb(vectordb_dir: Optional[Path] = None) -> Chroma:
    """Load (or create) the ChromaDB vector store."""
    vdb_path = vectordb_dir or DEFAULT_VECTORDB_DIR
    embeddings = GeminiEmbeddings()

    if vdb_path.exists():
        return Chroma(
            persist_directory=str(vdb_path),
            embedding_function=embeddings,
        )
    else:
        print(f"  ⚠  Vector DB not found at {vdb_path} — creating new one.")
        vdb_path.mkdir(parents=True, exist_ok=True)
        return Chroma(
            persist_directory=str(vdb_path),
            embedding_function=embeddings,
        )


def add_documents_to_vectordb(
    documents: List[Document],
    vectordb_dir: Optional[Path] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """
    Embed and store documents in ChromaDB in batches.
    Returns the number of documents successfully added.
    """
    if not documents:
        return 0

    vectordb = _get_vectordb(vectordb_dir)
    total = 0

    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        try:
            vectordb.add_documents(batch)
            total += len(batch)
            print(f"    → Embedded batch {i // batch_size + 1}: {len(batch)} docs ({total}/{len(documents)} total)")
        except Exception as e:
            print(f"    ✗ Batch {i // batch_size + 1} failed: {e}")

    return total


# ---------------------------------------------------------------------------
# Main ingestion functions
# ---------------------------------------------------------------------------

def ingest_311(
    conn: pymysql.connections.Connection,
    days: int = 30,
    vectordb_dir: Optional[Path] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    include_aggregates: bool = True,
    max_individual: int = 2000,
) -> Dict[str, Any]:
    """
    Full 311 ingestion pipeline:
      1. Fetch new records from MySQL (skipping already-ingested)
      2. Build individual record Documents
      3. Optionally build aggregate summary Documents
      4. Embed all into ChromaDB
      5. Track ingested record IDs in MySQL

    Returns stats dict.
    """
    stats = {
        "source": "311",
        "records_fetched": 0,
        "individual_docs_embedded": 0,
        "aggregate_docs_embedded": 0,
        "errors": [],
    }

    try:
        already_ingested = get_already_ingested_ids(conn, "311_request")
        print(f"  ℹ  {len(already_ingested)} 311 records already ingested — will skip.")

        records = fetch_311_records(
            conn, days=days, already_ingested=already_ingested, limit=max_individual
        )
        stats["records_fetched"] = len(records)
        print(f"  ✓ Fetched {len(records)} new 311 records (last {days} days)")

        if not records:
            print("  ℹ  No new 311 records to embed.")
            return stats

        # Individual record documents
        individual_docs, tracking_pairs = build_311_documents(records)
        print(f"  → Built {len(individual_docs)} individual 311 documents")

        embedded_count = add_documents_to_vectordb(individual_docs, vectordb_dir, batch_size)
        stats["individual_docs_embedded"] = embedded_count

        # Track ingestion
        if tracking_pairs:
            marked = mark_ingested(conn, "311_request", tracking_pairs)
            print(f"  ✓ Marked {marked} 311 records as ingested in tracking table")

        # Aggregate summaries
        if include_aggregates:
            window_label = f"last_{days}_days"
            agg_docs = build_311_aggregate_docs(records, window_label=window_label)
            print(f"  → Built {len(agg_docs)} 311 aggregate summary documents")

            agg_embedded = add_documents_to_vectordb(agg_docs, vectordb_dir, batch_size)
            stats["aggregate_docs_embedded"] = agg_embedded

    except Exception as e:
        error_msg = f"311 ingestion error: {e}"
        print(f"  ✗ {error_msg}")
        stats["errors"].append(error_msg)

    return stats


def ingest_crime(
    conn: pymysql.connections.Connection,
    days: int = 30,
    vectordb_dir: Optional[Path] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    include_aggregates: bool = True,
    max_individual: int = 2000,
) -> Dict[str, Any]:
    """
    Full crime/911 ingestion pipeline:
      1. Fetch new records from MySQL (skipping already-ingested)
      2. Build individual record Documents
      3. Optionally build aggregate summary Documents
      4. Embed all into ChromaDB
      5. Track ingested record IDs in MySQL

    Returns stats dict.
    """
    stats = {
        "source": "crime",
        "records_fetched": 0,
        "individual_docs_embedded": 0,
        "aggregate_docs_embedded": 0,
        "errors": [],
    }

    try:
        already_ingested = get_already_ingested_ids(conn, "crime_incident")
        print(f"  ℹ  {len(already_ingested)} crime records already ingested — will skip.")

        records = fetch_crime_records(
            conn, days=days, already_ingested=already_ingested, limit=max_individual
        )
        stats["records_fetched"] = len(records)
        print(f"  ✓ Fetched {len(records)} new crime records (last {days} days)")

        if not records:
            print("  ℹ  No new crime records to embed.")
            return stats

        # Individual record documents
        individual_docs, tracking_pairs = build_crime_documents(records)
        print(f"  → Built {len(individual_docs)} individual crime documents")

        embedded_count = add_documents_to_vectordb(individual_docs, vectordb_dir, batch_size)
        stats["individual_docs_embedded"] = embedded_count

        # Track ingestion
        if tracking_pairs:
            marked = mark_ingested(conn, "crime_incident", tracking_pairs)
            print(f"  ✓ Marked {marked} crime records as ingested in tracking table")

        # Aggregate summaries
        if include_aggregates:
            window_label = f"last_{days}_days"
            agg_docs = build_crime_aggregate_docs(records, window_label=window_label)
            print(f"  → Built {len(agg_docs)} crime aggregate summary documents")

            agg_embedded = add_documents_to_vectordb(agg_docs, vectordb_dir, batch_size)
            stats["aggregate_docs_embedded"] = agg_embedded

    except Exception as e:
        error_msg = f"Crime ingestion error: {e}"
        print(f"  ✗ {error_msg}")
        stats["errors"].append(error_msg)

    return stats


def run_ingestion(
    days: int = 30,
    source: str = "both",           # "311", "crime", or "both"
    vectordb_dir: Optional[Path] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    include_aggregates: bool = True,
    max_individual: int = 2000,
) -> Dict[str, Any]:
    """
    Orchestrate 311 and/or crime ingestion into the RAG vector store.
    Intended to be called from main_daily_ingestion.py or directly.

    Args:
        days:               How many days back to look for new records.
        source:             "311", "crime", or "both".
        vectordb_dir:       Path to ChromaDB directory (defaults to on_the_porch/vectordb_new).
        batch_size:         Number of documents per embedding API call.
        include_aggregates: Whether to also build & embed aggregate summaries.
        max_individual:     Cap on individual records per source per run.

    Returns:
        Dict with per-source stats and overall error list.
    """
    overall_stats: Dict[str, Any] = {
        "311": None,
        "crime": None,
        "total_errors": 0,
    }

    conn = None
    try:
        conn = _connect()
        ensure_tracking_table(conn)

        vdb_dir = Path(vectordb_dir) if vectordb_dir else None

        if source in ("311", "both"):
            print("\n  ── 311 Service Requests ──")
            stats_311 = ingest_311(
                conn,
                days=days,
                vectordb_dir=vdb_dir,
                batch_size=batch_size,
                include_aggregates=include_aggregates,
                max_individual=max_individual,
            )
            overall_stats["311"] = stats_311
            overall_stats["total_errors"] += len(stats_311.get("errors", []))

        if source in ("crime", "both"):
            print("\n  ── Crime Incident Reports ──")
            stats_crime = ingest_crime(
                conn,
                days=days,
                vectordb_dir=vdb_dir,
                batch_size=batch_size,
                include_aggregates=include_aggregates,
                max_individual=max_individual,
            )
            overall_stats["crime"] = stats_crime
            overall_stats["total_errors"] += len(stats_crime.get("errors", []))

    except Exception as e:
        print(f"\n  ✗ Fatal ingestion error: {e}")
        overall_stats["total_errors"] += 1

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    return overall_stats


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _print_summary(stats: Dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print("  311 & Crime → RAG Ingestion Summary")
    print("=" * 60)

    for source in ("311", "crime"):
        s = stats.get(source)
        if not s:
            continue
        print(f"\n  [{source.upper()}]")
        print(f"    Records fetched:      {s.get('records_fetched', 0)}")
        print(f"    Individual docs:      {s.get('individual_docs_embedded', 0)} embedded")
        print(f"    Aggregate summaries:  {s.get('aggregate_docs_embedded', 0)} embedded")
        if s.get("errors"):
            for err in s["errors"]:
                print(f"    ✗ Error: {err}")

    total_errs = stats.get("total_errors", 0)
    print(f"\n  Total errors: {total_errs}")
    print("=" * 60)
    if total_errs == 0:
        print("  ✅ Ingestion completed successfully!\n")
    else:
        print(f"  ⚠️  Ingestion completed with {total_errs} error(s).\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest Boston 311 and crime data into the RAG vector store."
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="How many days back to pull records (default: 30)"
    )
    parser.add_argument(
        "--source", choices=["311", "crime", "both"], default="both",
        help="Which data source to ingest (default: both)"
    )
    parser.add_argument(
        "--vectordb", type=str, default=None,
        help="Path to ChromaDB directory (default: on_the_porch/vectordb_new)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"Embedding batch size (default: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        "--no-aggregates", action="store_true",
        help="Skip aggregate summary documents"
    )
    parser.add_argument(
        "--max-records", type=int, default=2000,
        help="Max individual records per source per run (default: 2000)"
    )

    args = parser.parse_args()

    print(f"\n🚀 Starting 311 & Crime → RAG Ingestion")
    print(f"   Days back:      {args.days}")
    print(f"   Source:         {args.source}")
    print(f"   Aggregates:     {'no' if args.no_aggregates else 'yes'}")
    print(f"   Max records:    {args.max_records}")
    print(f"   Batch size:     {args.batch_size}")
    print(f"   Vector DB:      {args.vectordb or DEFAULT_VECTORDB_DIR}\n")

    stats = run_ingestion(
        days=args.days,
        source=args.source,
        vectordb_dir=Path(args.vectordb) if args.vectordb else None,
        batch_size=args.batch_size,
        include_aggregates=not args.no_aggregates,
        max_individual=args.max_records,
    )
    _print_summary(stats)
