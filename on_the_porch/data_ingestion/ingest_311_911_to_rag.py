"""
Ingest 311 service requests and crime incident data from MySQL into Chroma.

This stays additive to the existing ingestion pipeline: it does not replace the
structured SQL path, it only builds extra semantic retrieval documents.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymysql
from dotenv import load_dotenv
from langchain_core.documents import Document
from pymysql.cursors import DictCursor

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma

_THIS_FILE = Path(__file__).resolve()
_INGEST_DIR = _THIS_FILE.parent
_ROOT_DIR = _INGEST_DIR.parents[1]
_ON_THE_PORCH_DIR = _ROOT_DIR / "on_the_porch"
_RAG_STUFF_DIR = _ON_THE_PORCH_DIR / "rag stuff"
load_dotenv(_ROOT_DIR / ".env")

if str(_RAG_STUFF_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_STUFF_DIR))

from retrieval import GeminiEmbeddings  # noqa: E402

DEFAULT_VECTORDB_DIR = _ON_THE_PORCH_DIR / "vectordb_new"
RAG_TRACKING_TABLE = "rag_ingestion_log"
DEFAULT_BATCH_SIZE = 100

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DB", "rethink_ai_boston"),
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
}

_COLS_CRIME = [
    "incident_number", "offense_code", "offense_code_group", "offense_description",
    "district", "reporting_area", "shooting", "occurred_on_date", "year", "month",
    "day_of_week", "hour", "ucr_part", "street", "lat", "long",
]
_311_TABLE_CANDIDATES = ("service_requests_311", "bos311_data")
_311_FIELD_OPTIONS = {
    "record_id": ("case_id", "case_enquiry_id"),
    "open_dt": ("open_date", "open_dt"),
    "closed_dt": ("close_date", "closed_dt"),
    "case_status": ("case_status",),
    "closure_reason": ("closure_reason",),
    "case_title": ("case_title", "service_name", "case_topic"),
    "subject": ("subject", "assigned_department"),
    "reason": ("reason", "case_topic"),
    "type": ("type", "service_name"),
    "neighborhood": ("neighborhood",),
    "street": ("street", "full_address"),
    "latitude": ("latitude",),
    "longitude": ("longitude",),
}


def _connect() -> pymysql.connections.Connection:
    return pymysql.connect(**MYSQL_CONFIG)


def _table_exists(conn: pymysql.connections.Connection, table_name: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
        return cursor.fetchone() is not None


def _get_columns(conn: pymysql.connections.Connection, table_name: str) -> set[str]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            (table_name,),
        )
        return {row["COLUMN_NAME"] for row in cursor.fetchall()}


def ensure_tracking_table(conn: pymysql.connections.Connection) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {RAG_TRACKING_TABLE} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                source_type VARCHAR(50) NOT NULL,
                record_id VARCHAR(255) NOT NULL,
                chunk_id VARCHAR(64) NOT NULL,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_record (source_type, record_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
    conn.commit()


def get_already_ingested_ids(conn: pymysql.connections.Connection, source_type: str) -> set[str]:
    with conn.cursor() as cursor:
        cursor.execute(
            f"SELECT record_id FROM {RAG_TRACKING_TABLE} WHERE source_type = %s",
            (source_type,),
        )
        return {row["record_id"] for row in cursor.fetchall()}


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


def _detect_311_source(conn: pymysql.connections.Connection) -> Dict[str, Any]:
    for table_name in _311_TABLE_CANDIDATES:
        if not _table_exists(conn, table_name):
            continue
        columns = _get_columns(conn, table_name)
        selected = {}
        for alias, candidates in _311_FIELD_OPTIONS.items():
            selected[alias] = next((column for column in candidates if column in columns), None)
        if not selected["record_id"] or not selected["open_dt"]:
            continue
        select_parts = []
        for alias, column_name in selected.items():
            if column_name:
                select_parts.append(f"`{column_name}` AS `{alias}`")
            else:
                select_parts.append(f"NULL AS `{alias}`")
        return {
            "table": table_name,
            "select_sql": ", ".join(select_parts),
            "date_column": selected["open_dt"],
        }
    raise RuntimeError("No supported 311 table found. Expected service_requests_311 or bos311_data.")


def fetch_311_records(
    conn: pymysql.connections.Connection,
    days: int = 30,
    already_ingested: Optional[set[str]] = None,
    limit: int = 5000,
) -> List[Dict[str, Any]]:
    source = _detect_311_source(conn)
    since = datetime.now() - timedelta(days=days)
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {source['select_sql']}
            FROM `{source['table']}`
            WHERE `{source['date_column']}` >= %s
            ORDER BY `{source['date_column']}` DESC
            LIMIT %s
            """,
            (since.strftime("%Y-%m-%d %H:%M:%S"), limit),
        )
        rows = cursor.fetchall()
    if already_ingested:
        rows = [row for row in rows if str(row.get("record_id") or "") not in already_ingested]
    return rows


def _311_record_to_text(row: Dict[str, Any]) -> str:
    record_id = row.get("record_id") or "unknown"
    title = row.get("case_title") or "Service Request"
    neighborhood = row.get("neighborhood") or "unknown neighborhood"
    street = row.get("street") or ""
    subject = row.get("subject") or ""
    reason = row.get("reason") or ""
    request_type = row.get("type") or ""
    status = row.get("case_status") or "Unknown"
    open_dt = row.get("open_dt")
    closed_dt = row.get("closed_dt")
    closure_reason = row.get("closure_reason") or ""

    open_str = str(open_dt)[:10] if open_dt else "unknown date"
    closed_str = str(closed_dt)[:10] if closed_dt else None
    location_str = f"{street}, {neighborhood}".strip(", ") if street else neighborhood

    lines = [
        f"311 Service Request #{record_id}: {title}.",
        f"Location: {location_str}.",
    ]
    category_parts = [part for part in [subject, reason, request_type] if part]
    if category_parts:
        lines.append(f"Category: {' > '.join(category_parts)}.")
    lines.append(f"Reported: {open_str}. Status: {status}.")
    if closed_str:
        lines.append(f"Closed: {closed_str}.")
    if closure_reason:
        lines.append(f"Closure reason: {closure_reason}.")
    return " ".join(lines)


def build_311_documents(records: List[Dict[str, Any]]) -> Tuple[List[Document], List[Tuple[str, str]]]:
    documents: List[Document] = []
    tracking: List[Tuple[str, str]] = []

    for row in records:
        record_id = str(row.get("record_id") or "")
        if not record_id:
            continue
        text = _311_record_to_text(row)
        chunk_id = hashlib.sha256(text.encode()).hexdigest()[:16]
        open_date_str = str(row.get("open_dt") or "")[:10]
        metadata = {
            "doc_type": "311_request",
            "source": "Boston 311 Service Requests",
            "record_id": record_id,
            "case_title": row.get("case_title") or "",
            "neighborhood": row.get("neighborhood") or "",
            "case_status": row.get("case_status") or "",
            "open_date": open_date_str,
        }
        lat = row.get("latitude")
        lng = row.get("longitude")
        if lat and lng:
            try:
                metadata["lat"] = str(float(lat))
                metadata["lng"] = str(float(lng))
            except (ValueError, TypeError):
                pass
        documents.append(Document(page_content=text, metadata=metadata))
        tracking.append((record_id, chunk_id))

    return documents, tracking


def build_311_aggregate_docs(records: List[Dict[str, Any]], window_label: str = "recent") -> List[Document]:
    from collections import defaultdict

    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in records:
        neighborhood = (row.get("neighborhood") or "Unknown Neighborhood").strip()
        title = (row.get("case_title") or "General Request").strip()
        groups[(neighborhood, title)].append(row)

    documents: List[Document] = []
    for (neighborhood, title), group_records in groups.items():
        count = len(group_records)
        statuses = [row.get("case_status") or "Unknown" for row in group_records]
        open_count = sum(1 for status in statuses if str(status).lower() in {"open", "in progress", "create"})
        closed_count = sum(1 for status in statuses if str(status).lower() == "closed")
        dates = sorted({str(row.get("open_dt"))[:10] for row in group_records if row.get("open_dt")})
        if dates:
            date_range = f"{dates[0]} to {dates[-1]}" if len(dates) > 1 else dates[0]
        else:
            date_range = "unknown"
        text = (
            f"311 Summary for {neighborhood} — {title} ({window_label}): {count} service request(s) reported "
            f"between {date_range}. {open_count} open, {closed_count} resolved."
        )
        reasons = list({row.get("closure_reason") for row in group_records if row.get("closure_reason")})[:3]
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


def fetch_crime_records(
    conn: pymysql.connections.Connection,
    days: int = 30,
    already_ingested: Optional[set[str]] = None,
    limit: int = 5000,
) -> List[Dict[str, Any]]:
    since = datetime.now() - timedelta(days=days)
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {', '.join(_COLS_CRIME)}
            FROM crime_incident_reports
            WHERE occurred_on_date >= %s
            ORDER BY occurred_on_date DESC
            LIMIT %s
            """,
            (since.strftime("%Y-%m-%d %H:%M:%S"), limit),
        )
        rows = cursor.fetchall()
    if already_ingested:
        rows = [row for row in rows if str(row.get("incident_number") or "") not in already_ingested]
    return rows


def _crime_record_to_text(row: Dict[str, Any]) -> str:
    incident_num = row.get("incident_number") or "unknown"
    offense = row.get("offense_description") or row.get("offense_code_group") or "Unknown Offense"
    district = row.get("district") or "unknown district"
    street = row.get("street") or ""
    occurred = row.get("occurred_on_date")
    day_of_week = row.get("day_of_week") or ""
    hour = row.get("hour")
    shooting = row.get("shooting")
    ucr_part = row.get("ucr_part") or ""

    occurred_str = str(occurred)[:10] if occurred else "unknown date"
    time_str = ""
    if hour is not None:
        try:
            hour_value = int(hour)
            period = "AM" if hour_value < 12 else "PM"
            hour_12 = hour_value % 12 or 12
            time_str = f" at {hour_12}:00 {period}"
        except (ValueError, TypeError):
            pass

    location_str = f"{street}, District {district}".strip(", ") if street else f"District {district}"
    lines = [
        f"Crime Incident #{incident_num}: {offense}.",
        f"Location: {location_str}.",
        f"Occurred: {day_of_week} {occurred_str}{time_str}.",
    ]
    if shooting and str(shooting).strip().upper() in ("Y", "1", "TRUE"):
        lines.append("Shooting involved: Yes.")
    if ucr_part:
        lines.append(f"UCR Part: {ucr_part}.")
    return " ".join(lines)


def build_crime_documents(records: List[Dict[str, Any]]) -> Tuple[List[Document], List[Tuple[str, str]]]:
    documents: List[Document] = []
    tracking: List[Tuple[str, str]] = []

    for row in records:
        record_id = str(row.get("incident_number") or "")
        if not record_id:
            continue
        text = _crime_record_to_text(row)
        chunk_id = hashlib.sha256(text.encode()).hexdigest()[:16]
        metadata = {
            "doc_type": "crime_incident",
            "source": "Boston Crime Incident Reports",
            "record_id": record_id,
            "offense_description": row.get("offense_description") or "",
            "offense_code_group": row.get("offense_code_group") or "",
            "district": row.get("district") or "",
            "occurred_date": str(row.get("occurred_on_date") or "")[:10],
            "shooting": str(row.get("shooting") or ""),
        }
        lat = row.get("lat")
        lng = row.get("long")
        if lat and lng:
            try:
                metadata["lat"] = str(float(lat))
                metadata["lng"] = str(float(lng))
            except (ValueError, TypeError):
                pass
        documents.append(Document(page_content=text, metadata=metadata))
        tracking.append((record_id, chunk_id))

    return documents, tracking


def build_crime_aggregate_docs(records: List[Dict[str, Any]], window_label: str = "recent") -> List[Document]:
    from collections import defaultdict

    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in records:
        district = (row.get("district") or "Unknown District").strip()
        group_name = (row.get("offense_code_group") or "Other").strip()
        groups[(district, group_name)].append(row)

    documents: List[Document] = []
    for (district, group_name), group_records in groups.items():
        count = len(group_records)
        dates = sorted({str(row.get("occurred_on_date"))[:10] for row in group_records if row.get("occurred_on_date")})
        if dates:
            date_range = f"{dates[0]} to {dates[-1]}" if len(dates) > 1 else dates[0]
        else:
            date_range = "unknown"
        offense_counts: Dict[str, int] = {}
        for row in group_records:
            offense = row.get("offense_description") or "Other"
            offense_counts[offense] = offense_counts.get(offense, 0) + 1
        top_offenses = sorted(offense_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        offense_str = ", ".join(f"{offense} ({count})" for offense, count in top_offenses)
        shootings = sum(1 for row in group_records if str(row.get("shooting") or "").upper() in ("Y", "1", "TRUE"))
        text = f"Crime Summary for District {district} — {group_name} ({window_label}): {count} incident(s) between {date_range}."
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


def _get_vectordb(vectordb_dir: Optional[Path] = None) -> Chroma:
    vdb_path = vectordb_dir or DEFAULT_VECTORDB_DIR
    embeddings = GeminiEmbeddings()
    if not vdb_path.exists():
        vdb_path.mkdir(parents=True, exist_ok=True)
    return Chroma(persist_directory=str(vdb_path), embedding_function=embeddings)


def add_documents_to_vectordb(
    documents: List[Document],
    vectordb_dir: Optional[Path] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    if not documents:
        return 0
    vectordb = _get_vectordb(vectordb_dir)
    total = 0
    for index in range(0, len(documents), batch_size):
        batch = documents[index:index + batch_size]
        try:
            vectordb.add_documents(batch)
            total += len(batch)
            print(f"    Embedded batch {index // batch_size + 1}: {len(batch)} docs ({total}/{len(documents)} total)")
        except Exception as exc:
            print(f"    Batch {index // batch_size + 1} failed: {exc}")
    return total


def ingest_311(
    conn: pymysql.connections.Connection,
    days: int = 30,
    vectordb_dir: Optional[Path] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    include_aggregates: bool = True,
    max_individual: int = 2000,
) -> Dict[str, Any]:
    stats = {
        "source": "311",
        "records_fetched": 0,
        "individual_docs_embedded": 0,
        "aggregate_docs_embedded": 0,
        "errors": [],
    }
    try:
        already_ingested = get_already_ingested_ids(conn, "311_request")
        print(f"  {len(already_ingested)} 311 records already ingested; skipping duplicates.")
        records = fetch_311_records(conn, days=days, already_ingested=already_ingested, limit=max_individual)
        stats["records_fetched"] = len(records)
        print(f"  Fetched {len(records)} new 311 records")
        if not records:
            return stats
        individual_docs, tracking_pairs = build_311_documents(records)
        stats["individual_docs_embedded"] = add_documents_to_vectordb(individual_docs, vectordb_dir, batch_size)
        if tracking_pairs:
            mark_ingested(conn, "311_request", tracking_pairs)
        if include_aggregates:
            agg_docs = build_311_aggregate_docs(records, window_label=f"last_{days}_days")
            stats["aggregate_docs_embedded"] = add_documents_to_vectordb(agg_docs, vectordb_dir, batch_size)
    except Exception as exc:
        error_msg = f"311 ingestion error: {exc}"
        print(f"  {error_msg}")
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
    stats = {
        "source": "crime",
        "records_fetched": 0,
        "individual_docs_embedded": 0,
        "aggregate_docs_embedded": 0,
        "errors": [],
    }
    try:
        already_ingested = get_already_ingested_ids(conn, "crime_incident")
        print(f"  {len(already_ingested)} crime records already ingested; skipping duplicates.")
        records = fetch_crime_records(conn, days=days, already_ingested=already_ingested, limit=max_individual)
        stats["records_fetched"] = len(records)
        print(f"  Fetched {len(records)} new crime records")
        if not records:
            return stats
        individual_docs, tracking_pairs = build_crime_documents(records)
        stats["individual_docs_embedded"] = add_documents_to_vectordb(individual_docs, vectordb_dir, batch_size)
        if tracking_pairs:
            mark_ingested(conn, "crime_incident", tracking_pairs)
        if include_aggregates:
            agg_docs = build_crime_aggregate_docs(records, window_label=f"last_{days}_days")
            stats["aggregate_docs_embedded"] = add_documents_to_vectordb(agg_docs, vectordb_dir, batch_size)
    except Exception as exc:
        error_msg = f"Crime ingestion error: {exc}"
        print(f"  {error_msg}")
        stats["errors"].append(error_msg)
    return stats


def run_ingestion(
    days: int = 30,
    source: str = "both",
    vectordb_dir: Optional[Path] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    include_aggregates: bool = True,
    max_individual: int = 2000,
) -> Dict[str, Any]:
    overall_stats: Dict[str, Any] = {"311": None, "crime": None, "total_errors": 0}
    conn = None
    try:
        conn = _connect()
        ensure_tracking_table(conn)
        vdb_dir = Path(vectordb_dir) if vectordb_dir else None
        if source in ("311", "both"):
            print("\n  -- 311 Service Requests --")
            stats_311 = ingest_311(conn, days=days, vectordb_dir=vdb_dir, batch_size=batch_size, include_aggregates=include_aggregates, max_individual=max_individual)
            overall_stats["311"] = stats_311
            overall_stats["total_errors"] += len(stats_311.get("errors", []))
        if source in ("crime", "both"):
            print("\n  -- Crime Incident Reports --")
            stats_crime = ingest_crime(conn, days=days, vectordb_dir=vdb_dir, batch_size=batch_size, include_aggregates=include_aggregates, max_individual=max_individual)
            overall_stats["crime"] = stats_crime
            overall_stats["total_errors"] += len(stats_crime.get("errors", []))
    except Exception as exc:
        print(f"\n  Fatal ingestion error: {exc}")
        overall_stats["total_errors"] += 1
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return overall_stats


def _print_summary(stats: Dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print("  311 & Crime -> RAG Ingestion Summary")
    print("=" * 60)
    for source in ("311", "crime"):
        source_stats = stats.get(source)
        if not source_stats:
            continue
        print(f"\n  [{source.upper()}]")
        print(f"    Records fetched:      {source_stats.get('records_fetched', 0)}")
        print(f"    Individual docs:      {source_stats.get('individual_docs_embedded', 0)} embedded")
        print(f"    Aggregate summaries:  {source_stats.get('aggregate_docs_embedded', 0)} embedded")
        for error in source_stats.get("errors", []):
            print(f"    Error: {error}")
    print(f"\n  Total errors: {stats.get('total_errors', 0)}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Boston 311 and crime data into the RAG vector store.")
    parser.add_argument("--days", type=int, default=30, help="How many days back to pull records")
    parser.add_argument("--source", choices=["311", "crime", "both"], default="both", help="Which data source to ingest")
    parser.add_argument("--vectordb", type=str, default=None, help="Path to the ChromaDB directory")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Embedding batch size")
    parser.add_argument("--no-aggregates", action="store_true", help="Skip aggregate summary documents")
    parser.add_argument("--max-records", type=int, default=2000, help="Max individual records per source per run")
    args = parser.parse_args()

    stats = run_ingestion(
        days=args.days,
        source=args.source,
        vectordb_dir=Path(args.vectordb) if args.vectordb else None,
        batch_size=args.batch_size,
        include_aggregates=not args.no_aggregates,
        max_individual=args.max_records,
    )
    _print_summary(stats)
