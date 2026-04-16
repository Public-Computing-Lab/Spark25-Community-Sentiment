"""
Append active community/admin notes from MySQL into the shared Chroma vector DB.

Behavior:
1. If the vector DB directory does not exist, create it.
2. If it exists, append only notes that are not already present.
3. Ignore expires_at entirely; only active notes with non-empty content are used.

Usage:
    python "on_the_porch/rag stuff/ingest_community_notes.py"
    python "on_the_porch/rag stuff/ingest_community_notes.py" --vectordb ../vectordb_new
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import chromadb
import pymysql
from dotenv import load_dotenv
from langchain_core.documents import Document

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma  # type: ignore

_THIS_FILE = Path(__file__).resolve()
_RAG_DIR = _THIS_FILE.parent
_ROOT_DIR = _RAG_DIR.parent.parent
load_dotenv(_ROOT_DIR / ".env")

if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))

from retrieval import GeminiEmbeddings  # noqa: E402

DEFAULT_VECTORDB_DIR = (_RAG_DIR / "../vectordb_new").resolve()

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DB", "rethink_ai_boston"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}
print(MYSQL_CONFIG)


def _connect() -> pymysql.connections.Connection:
    return pymysql.connect(**MYSQL_CONFIG)


def _get_vectordb(vectordb_dir: Path) -> Chroma:
    embeddings = GeminiEmbeddings()
    if not vectordb_dir.exists():
        print(f"Vector DB not found at {vectordb_dir}; creating it now.")
        vectordb_dir.mkdir(parents=True, exist_ok=True)
    else:
        print(f"Using existing vector DB at {vectordb_dir}")

    return Chroma(
        persist_directory=str(vectordb_dir),
        embedding_function=embeddings,
    )


def fetch_active_community_notes(conn: pymysql.connections.Connection) -> list[dict[str, Any]]:
    """
    Fetch approved notes from admin_knowledge.
    expires_at is intentionally ignored per the requested behavior.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, content, category, source_flag_id, added_by, created_at
            FROM admin_knowledge
            WHERE active = TRUE
              AND content IS NOT NULL
              AND TRIM(content) <> ''
            ORDER BY created_at ASC, id ASC
            """
        )
        return list(cursor.fetchall())


def _note_to_document(note: dict[str, Any]) -> Document:
    note_id = str(note["id"])
    content = (note.get("content") or "").strip()
    category = (note.get("category") or "general").strip() or "general"
    added_by = (note.get("added_by") or "").strip()
    created_at = note.get("created_at")
    created_at_str = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or "")

    page_content = (
        f"Community note #{note_id}. "
        f"Category: {category}. "
        f"Content: {content}"
    )

    metadata = {
        "doc_type": "community_note",
        "source": "admin_knowledge",
        "note_id": note_id,
        "category": category,
        "added_by": added_by,
        "active": "true",
        "created_at": created_at_str,
    }

    source_flag_id = note.get("source_flag_id")
    if source_flag_id is not None:
        metadata["source_flag_id"] = str(source_flag_id)

    return Document(page_content=page_content, metadata=metadata)


def _get_existing_note_ids(vectordb_dir: Path) -> set[str]:
    if not vectordb_dir.exists():
        return set()

    client = chromadb.PersistentClient(path=str(vectordb_dir))
    try:
        collection = client.get_collection("langchain")
    except Exception:
        return set()

    count = collection.count()
    if count <= 0:
        return set()

    rows = collection.get(limit=count, include=["metadatas"])
    existing_note_ids: set[str] = set()
    for metadata in rows.get("metadatas") or []:
        if not metadata:
            continue
        if metadata.get("doc_type") == "community_note" and metadata.get("note_id"):
            existing_note_ids.add(str(metadata["note_id"]))
    return existing_note_ids


def ingest_community_notes(vectordb_dir: Path | None = None) -> dict[str, int]:
    vectordb_dir = (vectordb_dir or DEFAULT_VECTORDB_DIR).resolve()
    stats = {
        "notes_fetched": 0,
        "notes_added": 0,
        "notes_skipped_existing": 0,
    }

    conn = _connect()
    try:
        notes = fetch_active_community_notes(conn)
        stats["notes_fetched"] = len(notes)
        print(f"Fetched {len(notes)} active community notes from admin_knowledge")

        if not notes:
            return stats

        existing_note_ids = _get_existing_note_ids(vectordb_dir)
        print(f"Found {len(existing_note_ids)} community notes already in the vector DB")

        new_notes = [note for note in notes if str(note["id"]) not in existing_note_ids]
        stats["notes_skipped_existing"] = len(notes) - len(new_notes)

        if not new_notes:
            print("No new community notes to append.")
            return stats

        documents = [_note_to_document(note) for note in new_notes]
        document_ids = [f"community_note_{note['id']}" for note in new_notes]

        vectordb = _get_vectordb(vectordb_dir)
        vectordb.add_documents(documents=documents, ids=document_ids)
        stats["notes_added"] = len(documents)
        print(f"Added {len(documents)} community notes to the vector DB")
        return stats
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Append active admin/community notes into the shared Chroma vector DB."
    )
    parser.add_argument(
        "--vectordb",
        type=str,
        default=None,
        help="Path to the Chroma vector DB directory (defaults to on_the_porch/vectordb_new)",
    )
    args = parser.parse_args()

    stats = ingest_community_notes(Path(args.vectordb) if args.vectordb else None)
    print("\nSummary")
    print("-" * 40)
    print(f"Notes fetched:           {stats['notes_fetched']}")
    print(f"Notes added:             {stats['notes_added']}")
    print(f"Skipped existing notes:  {stats['notes_skipped_existing']}")


if __name__ == "__main__":
    main()
