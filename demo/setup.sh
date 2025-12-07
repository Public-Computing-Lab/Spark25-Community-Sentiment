#!/usr/bin/env bash
set -e

# Create a Python 3.11 virtual environment if it does not exist
if [ ! -d ".venv" ]; then
  if command -v python3.11 >/dev/null 2>&1; then
    python3.11 -m venv .venv
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m venv .venv
  else
    python -m venv .venv
  fi
fi

# Select the venv Python executable
if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
  PYTHON=".venv/Scripts/python.exe"
else
  PYTHON="python"
fi

# Install Python requirements
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r requirements.txt

# Unzip the ChromaDB/vector store if the archive exists
if [ -f "demo/vectordb_new.zip" ]; then
  unzip -o demo/vectordb_new.zip
fi

# Start MySQL demo database via Docker Compose
if command -v docker-compose >/dev/null 2>&1; then
  docker-compose -f demo/docker-compose.demo.yml up -d
else
  docker compose -f demo/docker-compose.demo.yml up -d
fi

# Activate the virtual environment for interactive use
if [ -f ".venv/bin/activate" ]; then
  . .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
  . .venv/Scripts/activate
fi
