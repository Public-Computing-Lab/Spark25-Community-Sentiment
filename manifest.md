# Project Manifest

## Context Summary
- Project: RethinkAI Dorchester community assistant combining SQL, RAG, and hybrid LLM routing.
- Key code: `on_the_porch/unified_chatbot.py` (routing + cache), `api/api_v2.py` (Flask API v2.0), static frontends `public/` (prod-style) and `test_frontend/` (tester UI).
- Data: MySQL tables (311/911/events) and Chroma-style vector DB in `on_the_porch/vectordb_new`. Ingestion lives in `on_the_porch/data_ingestion/`.
- Auth: API key header `RethinkAI-API-Key` is required; default sample key `banana`.

## Architecture
- **Client**: Vanilla HTML/CSS/JS frontends (`public`, `test_frontend`) call REST API at `http://127.0.0.1:8888` with API key; show chat, events, API tester.
- **API layer**: Flask app (`api/api_v2.py`) exposes `/chat`, `/log`, `/events`, `/health`. Uses session cookie + per-session in-memory cache. CORS enabled for all origins; credentials allowed.
- **Orchestration**: `unified_chatbot.py` routes a user message to SQL, RAG, or hybrid using LLM-based planner. Maintains retrieval cache (SQL rows, RAG chunks, metadata, answer) and can answer from history/cache.
- **Structured data path (SQL)**: `_run_sql` generates/executed SQL (MySQL via `mysql-connector-python`) against `rethink_ai_boston` DB, returns rows/columns plus generated answer.
- **Unstructured path (RAG)**: `retrieval` module (in `on_the_porch/rag stuff`) queries vector DB (`vectordb_new`) and feeds chunks/metadata to Gemini to compose answer.
- **Hybrid path**: Executes both SQL and RAG; merges answers and sources.
- **Logging**: `/log` and `/chat` call `log_interaction` to store query/response/mode in MySQL `interaction_log`; `/events` reads `weekly_events`.
- **Event data**: `/events` returns upcoming events (start_date within configurable days ahead) limited by query params.

## Components
- Backend: Flask app (`api/api_v2.py`), MySQL connection pool, session cache, endpoints `/chat`, `/log`, `/events`, `/health`.
- Core logic: `on_the_porch/unified_chatbot.py` (env bootstrap, vectordb path fix, LLM client setup, routing, cache mgmt, history reuse).
- Data ingestion: `on_the_porch/data_ingestion/` (Google Drive/email sync, DB setup, vector rebuild) — not part of runtime API but seeds data.
- Frontends: `public/` (production-like static UI) and `test_frontend/` (tester UI with API explorer); configurable `API_BASE_URL` and `API_KEY` in JS.
- Prompts/config: `api/prompts/`, `.env` at repo root (copy from `example_env.txt`).

## Dependencies (runtime highlights)
- Python 3.11+, Flask 3.x, mysql-connector-python, google-generativeai, dotenv, pandas/numpy, plotly/dash (legacy), httpx/requests.
- MySQL 8.x for structured data.
- Vector store: Chroma-style files under `on_the_porch/vectordb_new`.
- Frontend: vanilla JS/CSS, served via `python -m http.server` (no build).

## Data Flow
1. Browser sends chat message with API key → `/chat`.
2. Middleware validates key, sets session_id (cookie).
3. Per-session cache loaded; `_check_if_needs_new_data` may reuse cached SQL/RAG data for follow-ups.
4. `_route_question` selects `sql` | `rag` | `hybrid`; executes `_run_sql` (MySQL) or `_run_rag` (vector DB + Gemini) or `_run_hybrid` (both).
5. Response assembled with answer + sources (table names or rag metadata); cache stored per session.
6. Interaction logged to MySQL `interaction_log`. Frontend displays response, sources, mode; events panel uses `/events`.

## Assumptions
- `.env` at repo root provides `GEMINI_API_KEY`, `RETHINKAI_API_KEYS`, MySQL creds, `VECTORDB_DIR` (overridden to `on_the_porch/vectordb_new`), etc.
- Vector DB already populated by ingestion; MySQL has required tables (`weekly_events`, 311/911 tables, `interaction_log`).
- API and frontend run on same machine; CORS open but auth enforced by header key.
- Session cookies persist a week; in-memory caches acceptable for single-instance runs.

## Edge Cases / Failure Modes
- Missing/invalid API key → 401.
- MySQL unavailable → degraded health, 500s on `/chat`/`/events`/`/log`.
- Vector DB path mis-set if `on_the_porch/vectordb_new` missing; `_fix_retrieval_vectordb_path` attempts to correct.
- Cache growth: `_cleanup_old_caches` trims stale sessions (>60 min) and caps at 100; still process memory bound.
- Large conversations: history limited to last 10 messages when checking reuse.
- RAG metadata may lack `source`/`doc_type`; sources fallback to "Unknown".
- `/events` clamps `limit` (1–100) and `days_ahead` (1–30).

## Deployment Notes
- Dev: `python api/api_v2.py` (debug=True). Frontend: `cd public && python -m http.server 8000`.
- Production: run Flask via WSGI (e.g., gunicorn), set `FLASK_SESSION_COOKIE_SECURE=True`, restrict CORS origins, store secrets via env vars, add HTTPS terminator/reverse proxy. Configure DB backups/monitoring.
- Scaling: in-memory session cache is per-process; use shared cache (Redis) or disable caching for multi-instance deployments. Ensure vector DB path accessible to all workers.

## Improvement Opportunities
- Externalize session cache to Redis and add TTL metrics; evict by LRU.
- Add rate limiting per API key/session and structured audit logging.
- Strengthen `/events` query with pagination and date filters by end_date/timezones.
- Add unit/integration tests for routing decisions and cache reuse; stub LLM.
- Harden CORS to allowed origins and rotate API keys; consider JWT instead of static keys.
- Add health subchecks (vector DB, Gemini key validity).
- Provide Docker Compose for full stack (API + MySQL + static server) beyond demo DB.
- Document schema for 311/911 tables in `dataset-documentation/` and link from API docs.

## Assorted Notes
- Frontend default API key `'banana'` must match `.env` `RETHINKAI_API_KEYS`.
- `api/api.py` and `/data/query` legacy endpoints are deprecated; prefer `api_v2.py`.
- LLM defaults to `gemini-2.5-flash-lite`; override via env `GEMINI_MODEL`.

