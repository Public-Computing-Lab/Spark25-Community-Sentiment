## Demo Setup

This `demo/` folder contains a minimal, self-contained setup so an evaluator can bring up the project quickly without access to client credentials or infrastructure.

### Prerequisites

- **Python 3.11+**
- **Docker Desktop** (or Docker + Docker Compose)

### One-time data artifacts (already in repo)

- `demo/mysql_demo_dump.sql` – MySQL dump of a demo database
- `demo/docker-compose.demo.yml` – spins up MySQL with the demo data
- `demo/vectordb_new.zip` – compressed ChromaDB/vector store (you create this locally before committing)

### 1. Run the demo setup

From the project root:

- On Mac/Linux (or Windows with WSL / Git Bash):

  ```bash
  bash demo/setup.sh
  ```

- On Windows **without** WSL (Command Prompt / PowerShell):

  ```bat
  demo\setup_windows.bat
  ```

This will:
- Create a `.venv_demo` virtual environment just for the demo
- Install Python dependencies from the root `requirements.txt`
- Unzip `demo/vectordb_new.zip` so the vector DB is available
- Start a MySQL demo database using Docker (`mysql:8` image) and import `mysql_demo_dump.sql`

### 2. Environment variables

1. From the project root, copy the example env file to `.env`:
   ```bash
   cp example_env.txt .env
   ```
2. Open `.env` and fill in at least:
   - `GEMINI_API_KEY` (leave blank if you want to run without Gemini-based features)
   - Leave the demo DB values as-is if you are using the Docker demo:
     - `MYSQL_HOST=localhost`
     - `MYSQL_PORT=3306`
     - `MYSQL_USER=demo_user`
     - `MYSQL_PASSWORD=demo_pass`
     - `MYSQL_DB=sentiment_demo`

### 3. Run backend and frontend

From the project root, in **one terminal**:

```bash
cd api
python api_v2.py
```

The API will start on `http://127.0.0.1:8888`.

In **another terminal**:

```bash
cd public
python -m http.server 8000
```

Then open `http://localhost:8000` in your browser. Make sure the backend is running first.

### Notes

- The demo database and vector store are for evaluation only and are not up to date.
- For full production setup and data ingestion, see the main `README.md` and `on_the_porch/data_ingestion/README.md`.
