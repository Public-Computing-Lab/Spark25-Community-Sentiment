# Agent API v2.0 Documentation

A Flask-based REST API that exposes the Dorchester Community Chatbot's agentic system. This API provides intelligent question routing (SQL, RAG, or hybrid), conversation management, event retrieval, and interaction logging.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Installation & Setup](#installation--setup)
4. [Configuration](#configuration)
5. [Running the Server](#running-the-server)
6. [API Endpoints](#api-endpoints)
   - [POST /chat](#post-chat)
   - [POST /log](#post-log)
   - [PUT /log](#put-log)
   - [GET /events](#get-events)
   - [GET /health](#get-health)
7. [Authentication](#authentication)
8. [Error Handling](#error-handling)
9. [Database Schema](#database-schema)
10. [Internal Components](#internal-components)
11. [Testing](#testing)
12. [Deployment Notes](#deployment-notes)

---

## Overview

The Agent API v2.0 is a complete rewrite of the original RethinkAI API, designed to work with the unified agentic chatbot system. It combines:

- **SQL queries** for structured data (311 requests, crime reports, events)
- **RAG (Retrieval-Augmented Generation)** for document-based answers (policies, transcripts, newsletters)
- **Hybrid mode** that intelligently combines both approaches

The API automatically routes questions to the appropriate backend based on the nature of the query.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend Client                          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     api/api_v2.py (Flask)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  /chat       │  │  /events     │  │  /log        │          │
│  │  /health     │  │              │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  unified_chatbot.py (Agent Core)                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  _route_question() - Classifies: sql / rag / hybrid      │  │
│  └──────────────────────────────────────────────────────────┘  │
│           │                    │                    │           │
│           ▼                    ▼                    ▼           │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│  │  _run_sql()  │     │  _run_rag()  │     │ _run_hybrid()│    │
│  └──────────────┘     └──────────────┘     └──────────────┘    │
└─────────────────────────────────────────────────────────────────┘
          │                      │                      │
          ▼                      ▼                      ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│  sql_chat/app4   │   │  retrieval.py    │   │  Both combined   │
│  (MySQL queries) │   │  (Chroma VectorDB)│   │                  │
└──────────────────┘   └──────────────────┘   └──────────────────┘
          │                      │
          ▼                      ▼
┌──────────────────┐   ┌──────────────────┐
│  MySQL Database  │   │  Chroma VectorDB │
│  - crime_reports │   │  - transcripts   │
│  - weekly_events │   │  - policies      │
│  - 311 requests  │   │  - newsletters   │
└──────────────────┘   └──────────────────┘
```

---

## Installation & Setup

### Prerequisites

- Python 3.9+
- MySQL 8.0+
- Virtual environment with required packages

### Install Dependencies

```bash
# Navigate to project root
cd ml-misi-community-sentiment

# Activate virtual environment
# Windows:
on_the_porch\pocEnv\Scripts\activate
# Linux/Mac:
source on_the_porch/pocEnv/bin/activate

# Install required packages
pip install flask flask-cors python-dotenv pymysql google-generativeai chromadb
```

### Required Environment Variables

Create a `.env` file in the project root or `on_the_porch/` directory:

```env
# Gemini API (required)
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash-lite

# MySQL Database (required)
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your-password
MYSQL_DB=rethink_ai_boston

# API Configuration (optional)
API_HOST=127.0.0.1
API_PORT=8888
API_KEYS=key1,key2,key3  # Comma-separated, leave empty to disable auth

# Flask Settings (optional)
FLASK_SECRET_KEY=your-secret-key
FLASK_SESSION_COOKIE_SECURE=False
```

---

## Configuration

The `Config` class in `api_v2.py` manages all configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `API_VERSION` | `v2.0` | API version string |
| `API_KEYS` | `[]` | List of valid API keys (empty = no auth) |
| `HOST` | `127.0.0.1` | Server bind address |
| `PORT` | `8888` | Server port |
| `SECRET_KEY` | `agent-api-secret-2025` | Flask session secret |
| `SESSION_COOKIE_SECURE` | `False` | Require HTTPS for cookies |
| `MYSQL_HOST` | `127.0.0.1` | MySQL server host |
| `MYSQL_PORT` | `3306` | MySQL server port |
| `MYSQL_USER` | `root` | MySQL username |
| `MYSQL_PASSWORD` | `""` | MySQL password |
| `MYSQL_DB` | `rethink_ai_boston` | MySQL database name |

---

## Running the Server

### Development Mode

```bash
# From project root with virtual environment activated
python api/api_v2.py
```

Output:
```
✓ interaction_log table ready

🚀 Agent API v2.0
   Host: 127.0.0.1:8888
   Auth: Disabled

 * Serving Flask app 'api_v2'
 * Debug mode: on
 * Running on http://127.0.0.1:8888
```

### Production Mode

For production, use a WSGI server like Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8888 api.api_v2:app
```

---

## API Endpoints

### POST /chat

Main chat endpoint. Sends a question to the agent and receives an intelligent response with source citations.

**Request Headers:**
```
Content-Type: application/json
X-API-Key: your-api-key  (if authentication is enabled)
```

**Request Body:**
```json
{
  "message": "What events are happening this weekend?",
  "conversation_history": [
    {"role": "user", "content": "previous question"},
    {"role": "assistant", "content": "previous answer"}
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | The user's question |
| `conversation_history` | array | No | Previous conversation for context |

**Response (200 OK):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": "Here are the events happening this weekend in Dorchester...",
  "sources": [
    {"type": "sql", "table": "weekly_events"},
    {"type": "rag", "source": "newsletter.pdf", "doc_type": "client_upload"}
  ],
  "mode": "hybrid",
  "log_id": 42
}
```

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | UUID for this session |
| `response` | string | The agent's answer |
| `sources` | array | Citations for the answer |
| `mode` | string | Routing mode used: `sql`, `rag`, `hybrid`, or `history` |
| `log_id` | integer | ID of the logged interaction |

**Response Modes:**

- `sql` - Answer came from MySQL database queries
- `rag` - Answer came from vector database (documents)
- `hybrid` - Answer combined both SQL and RAG
- `history` - Answer derived from conversation history only

**Error Response (400):**
```json
{
  "error": "Message is required"
}
```

**Error Response (500):**
```json
{
  "error": "Internal server error: [details]"
}
```

**Example (curl):**
```bash
curl -X POST http://127.0.0.1:8888/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How many 311 requests were filed last month?"}'
```

---

### POST /log

Create a new interaction log entry.

**Request Body:**
```json
{
  "client_query": "What events are happening?",
  "app_response": "Here are the events...",
  "mode": "hybrid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_query` | string | Yes | The user's question |
| `app_response` | string | No | The bot's response |
| `mode` | string | No | The routing mode used |

**Response (201 Created):**
```json
{
  "log_id": 42,
  "message": "Log entry created"
}
```

**Example (curl):**
```bash
curl -X POST http://127.0.0.1:8888/log \
  -H "Content-Type: application/json" \
  -d '{"client_query": "test", "app_response": "test response", "mode": "sql"}'
```

---

### PUT /log

Update an existing log entry (e.g., add user feedback).

**Request Body:**
```json
{
  "log_id": 42,
  "client_response_rating": "helpful"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `log_id` | integer | Yes | ID of the log entry to update |
| `client_response_rating` | string | No | User's feedback rating |

**Response (200 OK):**
```json
{
  "log_id": 42,
  "message": "Log entry updated"
}
```

**Example (curl):**
```bash
curl -X PUT http://127.0.0.1:8888/log \
  -H "Content-Type: application/json" \
  -d '{"log_id": 42, "client_response_rating": "helpful"}'
```

---

### GET /events

Fetch upcoming community events for dashboard display.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 10 | Max events to return (1-100) |
| `days_ahead` | integer | 7 | How many days ahead to look (1-30) |

**Response (200 OK):**
```json
{
  "events": [
    {
      "id": 170,
      "event_name": "Community Meeting",
      "event_date": "Saturday, December 7",
      "start_date": "2025-12-07",
      "end_date": "2025-12-07",
      "start_time": "10:00:00",
      "end_time": "12:00:00",
      "description": "Monthly neighborhood meeting at the community center.",
      "source": "newsletter_dec2025.pdf"
    }
  ],
  "total": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Event ID |
| `event_name` | string | Event title |
| `event_date` | string | Human-readable date label |
| `start_date` | string | ISO date (YYYY-MM-DD) |
| `end_date` | string | ISO date or null |
| `start_time` | string | Time (HH:MM:SS) or null |
| `end_time` | string | Time or null |
| `description` | string | Event description (from raw_text) |
| `source` | string | Source PDF filename |

**Example (curl):**
```bash
curl "http://127.0.0.1:8888/events?limit=5&days_ahead=14"
```

---

### GET /health

Health check endpoint for monitoring and load balancers.

**Response (200 OK):**
```json
{
  "status": "ok",
  "version": "v2.0",
  "database": "connected"
}
```

**Response (Degraded):**
```json
{
  "status": "degraded",
  "version": "v2.0",
  "database": "disconnected"
}
```

**Example (curl):**
```bash
curl http://127.0.0.1:8888/health
```

---

## Authentication

Authentication is optional and controlled by the `API_KEYS` environment variable.

### Enabling Authentication

Set `API_KEYS` in your `.env` file:
```env
API_KEYS=my-secret-key-1,my-secret-key-2,production-key
```

### Using Authentication

Include the API key in the `X-API-Key` header:

```bash
curl -X POST http://127.0.0.1:8888/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: my-secret-key-1" \
  -d '{"message": "Hello"}'
```

### Authentication Errors

**401 Unauthorized:**
```json
{
  "error": "Invalid or missing API key"
}
```

### Disabling Authentication

Leave `API_KEYS` empty or unset:
```env
API_KEYS=
```

---

## Error Handling

All errors return JSON with an `error` field:

| Status Code | Meaning | Example |
|-------------|---------|---------|
| 400 | Bad Request | Missing required field |
| 401 | Unauthorized | Invalid API key |
| 500 | Server Error | Database connection failed |

**Standard Error Format:**
```json
{
  "error": "Description of what went wrong"
}
```

---

## Database Schema

### interaction_log Table

Auto-created on server startup if it doesn't exist.

```sql
CREATE TABLE interaction_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(255),
    app_version VARCHAR(50),
    data_selected TEXT,
    data_attributes TEXT,
    prompt_preamble TEXT,
    client_query TEXT,
    app_response TEXT,
    client_response_rating VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Primary key |
| `session_id` | VARCHAR(255) | UUID session identifier |
| `app_version` | VARCHAR(50) | API version (e.g., "v2.0") |
| `data_selected` | TEXT | Routing mode used |
| `client_query` | TEXT | User's question |
| `app_response` | TEXT | Bot's response |
| `client_response_rating` | VARCHAR(50) | User feedback |
| `created_at` | TIMESTAMP | When the log was created |

### weekly_events Table

Used by the `/events` endpoint. Created by `mysql_setup.py`.

```sql
CREATE TABLE weekly_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source_pdf VARCHAR(255),
    page_number INT,
    event_name VARCHAR(255) NOT NULL,
    event_date VARCHAR(255) NOT NULL,
    start_date DATE,
    end_date DATE,
    start_time TIME,
    end_time TIME,
    raw_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Internal Components

### Imported from unified_chatbot.py

| Function | Purpose |
|----------|---------|
| `_bootstrap_env()` | Load environment variables |
| `_fix_retrieval_vectordb_path()` | Configure vector DB path |
| `_check_if_needs_new_data()` | Determine if question needs new retrieval |
| `_route_question()` | Classify question as sql/rag/hybrid |
| `_run_sql()` | Execute SQL-based answer generation |
| `_run_rag()` | Execute RAG-based answer generation |
| `_run_hybrid()` | Combine SQL and RAG answers |
| `_answer_from_history()` | Answer from conversation context only |

### Helper Functions in api_v2.py

| Function | Purpose |
|----------|---------|
| `get_db_connection()` | Create MySQL connection |
| `ensure_interaction_log_table()` | Create log table if missing |
| `extract_sources()` | Parse sources from result for citations |
| `log_interaction()` | Insert/update interaction logs |

---

## Testing

### Using the Test Script

A test script is provided at `api/test_api_v2.py`:

```bash
# With the server running
python api/test_api_v2.py
```

**Expected Output:**
```
Testing API v2 endpoints...

=== Testing /health ===
Status: 200
Response: {"status": "ok", "version": "v2.0", "database": "connected"}

=== Testing /events ===
Status: 200
Total events: 3

=== Testing /log (POST) ===
Status: 201
Response: {"log_id": 1, "message": "Log entry created"}

=== Testing /chat ===
Status: 200
Mode: hybrid
Sources: [...]

==================================================
SUMMARY
==================================================
Health: ✓ PASS
Events: ✓ PASS
Log POST: ✓ PASS
Chat: ✓ PASS
```

### Manual Testing with curl

```bash
# Health check
curl http://127.0.0.1:8888/health

# Get events
curl "http://127.0.0.1:8888/events?limit=5"

# Chat (simple)
curl -X POST http://127.0.0.1:8888/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is happening in Dorchester?"}'

# Chat (with history)
curl -X POST http://127.0.0.1:8888/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me more about that",
    "conversation_history": [
      {"role": "user", "content": "What events are this week?"},
      {"role": "assistant", "content": "There are 3 events..."}
    ]
  }'

# Create log
curl -X POST http://127.0.0.1:8888/log \
  -H "Content-Type: application/json" \
  -d '{"client_query": "test", "app_response": "response"}'

# Update log with feedback
curl -X PUT http://127.0.0.1:8888/log \
  -H "Content-Type: application/json" \
  -d '{"log_id": 1, "client_response_rating": "helpful"}'
```

---

## Deployment Notes

### CORS Configuration

CORS is enabled for all origins by default:
```python
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})
```

For production, restrict to specific origins:
```python
CORS(app, resources={r"/*": {"origins": ["https://yourdomain.com"]}})
```

### Session Management

- Sessions are stored server-side with a 7-day lifetime
- Session IDs are UUIDs generated automatically
- Cookies are HTTP-only by default
- Set `FLASK_SESSION_COOKIE_SECURE=True` for HTTPS-only cookies

### Production Checklist

1. Set strong `FLASK_SECRET_KEY`
2. Enable `API_KEYS` authentication
3. Set `FLASK_SESSION_COOKIE_SECURE=True`
4. Use a WSGI server (Gunicorn, uWSGI)
5. Put behind a reverse proxy (Nginx, Cloudflare)
6. Enable HTTPS
7. Restrict CORS origins
8. Set up monitoring for `/health` endpoint

### Example Nginx Configuration

```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8888;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## File Structure

```
ml-misi-community-sentiment/
├── api/
│   ├── api_v2.py           # Main API file
│   └── test_api_v2.py      # Test script
├── on_the_porch/
│   ├── unified_chatbot.py  # Agent core logic
│   ├── api_readme.md       # This documentation
│   ├── sql_chat/
│   │   └── app4.py         # SQL query generation
│   ├── rag stuff/
│   │   └── retrieval.py    # Vector DB retrieval
│   ├── vectordb_new/       # Chroma vector database
│   └── pocEnv/             # Virtual environment
└── .env                    # Environment variables
```

---

## Changelog

### v2.0 (2025-11-28)
- Complete rewrite using unified_chatbot.py agent
- Intelligent question routing (SQL/RAG/hybrid)
- Source citations in responses
- Conversation history support
- Auto-creation of interaction_log table
- Simplified endpoint structure

---

## Support

For issues or questions:
1. Check the `/health` endpoint for system status
2. Review server logs for error details
3. Ensure all environment variables are set correctly
4. Verify MySQL and Chroma databases are accessible

