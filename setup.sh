#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  if command -v python3.11 >/dev/null 2>&1; then
    python3.11 -m venv .venv
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m venv .venv
  else
    python -m venv .venv
  fi
fi

if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
  PYTHON=".venv/Scripts/python.exe"
else
  echo "Could not find the virtualenv Python executable." >&2
  exit 1
fi

echo "Using Python: $PYTHON"

echo "Installing dependencies..."
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r requirements.txt

echo "Creating empty vector DB..."
"$PYTHON" -c 'from pathlib import Path; import os; import chromadb; from dotenv import load_dotenv; root = Path.cwd(); load_dotenv(root / ".env"); raw = os.getenv("VECTORDB_DIR", "on_the_porch/vectordb_new"); db_path = Path(raw) if Path(raw).is_absolute() else (root / raw).resolve(); db_path.mkdir(parents=True, exist_ok=True); chromadb.PersistentClient(path=str(db_path)).get_or_create_collection("langchain"); print(f"Empty vector DB ready at {db_path}")'

echo "Running Google Drive ingestion..."
"$PYTHON" "on_the_porch/data_ingestion/google_drive_to_vectordb.py"

echo "Running Boston Open Data sync..."
"$PYTHON" "on_the_porch/data_ingestion/boston_data_sync/boston_data_sync.py"

echo "Running RSS Wayback ingestion..."
"$PYTHON" "on_the_porch/rag stuff/ingest_rss_wayback.py"

echo "Running DotNews first-time ingestion..."
"$PYTHON" "on_the_porch/data_ingestion/run_dotnews_ingest_v2.py" --first-time

echo
echo "Setup complete."
