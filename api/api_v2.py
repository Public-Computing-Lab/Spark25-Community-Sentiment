"""
api_v2.py

Agent-powered API for the Dorchester community chatbot.
Exposes the unified SQL + RAG chatbot via REST endpoints.

Endpoints:
- POST /chat - Main chat interaction with source citations
- POST/PUT /log - Interaction logging and feedback
- GET /events - Fetch upcoming community events for dashboard
"""

import os
import sys
import json
import uuid
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, request, jsonify, g, session
from flask_cors import CORS
from dotenv import load_dotenv
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool

# Setup paths to import from on_the_porch
_THIS_FILE = Path(__file__).resolve()
_API_DIR = _THIS_FILE.parent
_ROOT_DIR = _API_DIR.parent
load_dotenv(_ROOT_DIR / ".env")
_ON_THE_PORCH_DIR = _ROOT_DIR / "on_the_porch"

# Add on_the_porch to path for imports
if str(_ON_THE_PORCH_DIR) not in sys.path:
    sys.path.insert(0, str(_ON_THE_PORCH_DIR))

# Add rag stuff directory
_RAG_DIR = _ON_THE_PORCH_DIR / "rag stuff"
if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))

# Import unified chatbot functions
from unified_chatbot import (
    _bootstrap_env,
    _fix_retrieval_vectordb_path,
    _get_llm_client,
    _check_if_needs_new_data,
    _route_question,
    _run_sql,
    _run_rag,
    _run_hybrid,
    _answer_from_history,
    create_empty_cache,
    build_retrieval_cache,
)

# In-memory cache storage per session (for retrieval data)
# Key: session_id, Value: retrieval cache dict
_session_caches: Dict[str, Dict[str, Any]] = {}

# Cache settings
_CACHE_MAX_SESSIONS = 100  # Max number of sessions to keep in cache
_CACHE_MAX_AGE_MINUTES = 60  # Max age of cache before considered stale


def _cleanup_old_caches():
    """Remove old caches to prevent memory growth."""
    if len(_session_caches) <= _CACHE_MAX_SESSIONS:
        return
    
    # Sort by timestamp and remove oldest
    now = datetime.datetime.now()
    to_remove = []
    
    for sid, cache in _session_caches.items():
        ts = cache.get("timestamp")
        if ts:
            try:
                cache_time = datetime.datetime.fromisoformat(ts)
                age_minutes = (now - cache_time).total_seconds() / 60
                if age_minutes > _CACHE_MAX_AGE_MINUTES:
                    to_remove.append(sid)
            except Exception:
                pass
    
    # Remove stale caches
    for sid in to_remove:
        del _session_caches[sid]
    
    # If still over limit, remove oldest
    if len(_session_caches) > _CACHE_MAX_SESSIONS:
        # Sort by timestamp
        sorted_sessions = sorted(
            _session_caches.items(),
            key=lambda x: x[1].get("timestamp", ""),
        )
        # Remove oldest until under limit
        for sid, _ in sorted_sessions[:len(_session_caches) - _CACHE_MAX_SESSIONS]:
            del _session_caches[sid]


# =============================================================================
# Configuration
# =============================================================================
class Config:
    API_VERSION = "v2.0"
    _raw_keys = os.getenv("RETHINKAI_API_KEYS", "").split(",")
    RETHINKAI_API_KEYS = [k.strip() for k in _raw_keys if k.strip()]
    HOST = os.getenv("API_HOST", "127.0.0.1")
    PORT = int(os.getenv("API_PORT", "8888"))
    
    # Flask settings
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "agent-api-secret-2025")
    SESSION_COOKIE_SECURE = os.getenv("FLASK_SESSION_COOKIE_SECURE", "False").lower() == "true"
    
    # Database settings
    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DB = os.getenv("MYSQL_DB", "rethink_ai_boston")


# =============================================================================
# Database Connection Pool
# =============================================================================
# Create connection pool
db_pool = MySQLConnectionPool(
    host=Config.MYSQL_HOST,
    port=Config.MYSQL_PORT,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB,
    pool_name="api_v2_pool",
    pool_size=10
)


# =============================================================================
# Flask App Setup
# =============================================================================
app = Flask(__name__)
app.config.update(
    SECRET_KEY=Config.SECRET_KEY,
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=7),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=Config.SESSION_COOKIE_SECURE,
)

# Enable CORS
CORS(
    app,
    supports_credentials=True,
    expose_headers=["RethinkAI-API-Key"],
    resources={r"/*": {"origins": "*"}},
    allow_headers=["Content-Type", "RethinkAI-API-Key"],
)


# =============================================================================
# Database Connection
# =============================================================================
def get_db_connection():
    """Get a database connection from the connection pool."""
    return db_pool.get_connection()


def ensure_interaction_log_table():
    """Create interaction_log table if it doesn't exist."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interaction_log (
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
            )
        """)
        conn.commit()
        print("✓ interaction_log table ready")
    except Exception as e:
        print(f"Warning: Could not ensure interaction_log table: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =============================================================================
# Middleware
# =============================================================================
@app.before_request
def before_request_handler():
    """Validate API key and setup session."""
    # Skip auth for OPTIONS (CORS preflight)
    if request.method == "OPTIONS":
        return ("", 204)
    
    # Validate API key (mandatory)
    rethinkai_api_key = request.headers.get("RethinkAI-API-Key")
    if not rethinkai_api_key or rethinkai_api_key not in Config.RETHINKAI_API_KEYS:
        return jsonify({"error": "Invalid or missing API key"}), 401
    
    # Ensure session ID exists
    if "session_id" not in session:
        session.permanent = True
        session["session_id"] = str(uuid.uuid4())
    
    g.session_id = session.get("session_id")


# =============================================================================
# Helper Functions
# =============================================================================
def extract_sources(mode: str, result: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract source citations from the result based on mode."""
    sources = []
    
    if mode == "sql":
        # Extract table name from SQL result
        sql_query = result.get("sql", "")
        if sql_query:
            # Simple extraction - look for FROM clause
            import re
            match = re.search(r'FROM\s+`?(\w+)`?', sql_query, re.IGNORECASE)
            if match:
                sources.append({"type": "sql", "table": match.group(1)})
    
    elif mode == "rag":
        # Extract from RAG metadata
        metadata = result.get("metadata", [])
        seen = set()
        for meta in metadata[:5]:  # Limit to 5 sources
            source = meta.get("source", "Unknown")
            doc_type = meta.get("doc_type", "unknown")
            key = f"{source}:{doc_type}"
            if key not in seen:
                seen.add(key)
                sources.append({
                    "type": "rag",
                    "source": source,
                    "doc_type": doc_type
                })
    
    elif mode == "hybrid":
        # Combine SQL and RAG sources
        sql_part = result.get("sql", {})
        rag_part = result.get("rag", {})
        
        # SQL source
        sql_query = sql_part.get("sql", "") if isinstance(sql_part, dict) else ""
        if sql_query:
            import re
            match = re.search(r'FROM\s+`?(\w+)`?', sql_query, re.IGNORECASE)
            if match:
                sources.append({"type": "sql", "table": match.group(1)})
        
        # RAG sources
        rag_metadata = rag_part.get("metadata", []) if isinstance(rag_part, dict) else []
        seen = set()
        for meta in rag_metadata[:3]:  # Limit to 3 RAG sources in hybrid
            source = meta.get("source", "Unknown")
            doc_type = meta.get("doc_type", "unknown")
            key = f"{source}:{doc_type}"
            if key not in seen:
                seen.add(key)
                sources.append({
                    "type": "rag",
                    "source": source,
                    "doc_type": doc_type
                })
    
    return sources


def log_interaction(
    session_id: str,
    client_query: str,
    app_response: str,
    mode: str = "",
    log_id: Optional[int] = None,
    rating: str = "",
) -> Optional[int]:
    """Log an interaction to the database."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if log_id:
            # Update existing entry
            update_fields = []
            values = []
            if rating:
                update_fields.append("client_response_rating = %s")
                values.append(rating)
            if app_response:
                update_fields.append("app_response = %s")
                values.append(app_response)
            
            if update_fields:
                values.append(log_id)
                query = f"UPDATE interaction_log SET {', '.join(update_fields)} WHERE id = %s"
                cursor.execute(query, values)
            conn.commit()
            return log_id
        else:
            # Insert new entry
            query = """
                INSERT INTO interaction_log 
                (session_id, app_version, client_query, app_response, data_selected)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(query, (session_id, Config.API_VERSION, client_query, app_response, mode))
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        print(f"Error logging interaction: {e}")
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =============================================================================
# Endpoints
# =============================================================================

@app.route("/chat", methods=["POST"])
def chat():
    """
    Main chat endpoint.
    
    Request JSON:
    {
        "message": "What events are happening this weekend?",
        "conversation_history": [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous answer"}
        ]
    }
    
    Response JSON:
    {
        "session_id": "uuid",
        "response": "Here are the events...",
        "sources": [...],
        "mode": "hybrid",
        "log_id": 123
    }
    """
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    conversation_history = data.get("conversation_history", [])
    
    if not message:
        return jsonify({"error": "Message is required"}), 400
    
    session_id = g.session_id
    
    # Cleanup old caches periodically
    _cleanup_old_caches()
    
    # Get or create retrieval cache for this session
    retrieval_cache = _session_caches.get(session_id, create_empty_cache())
    
    try:
        # Check if we can answer from history and/or cache
        has_history = conversation_history and len(conversation_history) > 0
        has_cache = retrieval_cache and retrieval_cache.get("mode")
        
        if has_history or has_cache:
            history_check = _check_if_needs_new_data(message, conversation_history, retrieval_cache)
        else:
            history_check = {"needs_new_data": True, "reason": "No history or cache"}
        
        if not history_check.get("needs_new_data", True) and (has_history or has_cache):
            # Answer from conversation history and/or cache
            answer = _answer_from_history(message, conversation_history, retrieval_cache)
            mode = "history"
            sources = []
            result = {"answer": answer}
        else:
            # Route the question and execute
            plan = _route_question(message)
            mode = plan.get("mode", "hybrid")
            
            if mode == "sql":
                result = _run_sql(message, conversation_history)
                # Build and store retrieval cache
                _session_caches[session_id] = build_retrieval_cache(
                    mode="sql",
                    question=message,
                    answer=result.get("answer", ""),
                    sql_result=result.get("result"),
                    sql_query=result.get("sql"),
                )
            elif mode == "rag":
                result = _run_rag(message, plan, conversation_history)
                # Build and store retrieval cache
                _session_caches[session_id] = build_retrieval_cache(
                    mode="rag",
                    question=message,
                    answer=result.get("answer", ""),
                    rag_chunks=result.get("chunks"),
                    rag_metadata=result.get("metadata"),
                )
            else:  # hybrid
                result = _run_hybrid(message, plan, conversation_history)
                sqlp = result.get("sql", {})
                ragp = result.get("rag", {})
                # Build and store retrieval cache
                _session_caches[session_id] = build_retrieval_cache(
                    mode="hybrid",
                    question=message,
                    answer=result.get("answer", ""),
                    sql_result=sqlp.get("result") if isinstance(sqlp, dict) else None,
                    sql_query=sqlp.get("sql") if isinstance(sqlp, dict) else None,
                    rag_chunks=ragp.get("chunks") if isinstance(ragp, dict) else None,
                    rag_metadata=ragp.get("metadata") if isinstance(ragp, dict) else None,
                )
            
            answer = result.get("answer", "I couldn't find an answer to your question.")
            sources = extract_sources(mode, result)
        
        # Log the interaction
        log_id = log_interaction(
            session_id=session_id,
            client_query=message,
            app_response=answer,
            mode=mode,
        )
        
        return jsonify({
            "session_id": session_id,
            "response": answer,
            "sources": sources,
            "mode": mode,
            "log_id": log_id,
        })
    
    except Exception as e:
        print(f"Error in /chat: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route("/log", methods=["POST", "PUT"])
def log_endpoint():
    """
    Log interactions and feedback.
    
    POST - Create new log entry:
    {
        "client_query": "user question",
        "app_response": "bot answer",
        "mode": "hybrid"
    }
    
    PUT - Update existing entry (e.g., add rating):
    {
        "log_id": 123,
        "client_response_rating": "helpful"
    }
    """
    data = request.get_json() or {}
    session_id = g.session_id
    
    if request.method == "POST":
        client_query = data.get("client_query", "")
        app_response = data.get("app_response", "")
        mode = data.get("mode", "")
        
        if not client_query:
            return jsonify({"error": "client_query is required"}), 400
        
        log_id = log_interaction(
            session_id=session_id,
            client_query=client_query,
            app_response=app_response,
            mode=mode,
        )
        
        if log_id:
            return jsonify({"log_id": log_id, "message": "Log entry created"}), 201
        else:
            return jsonify({"error": "Failed to create log entry"}), 500
    
    elif request.method == "PUT":
        log_id = data.get("log_id")
        rating = data.get("client_response_rating", "")
        
        if not log_id:
            return jsonify({"error": "log_id is required"}), 400
        
        updated_id = log_interaction(
            session_id=session_id,
            client_query="",
            app_response="",
            log_id=log_id,
            rating=rating,
        )
        
        if updated_id:
            return jsonify({"log_id": updated_id, "message": "Log entry updated"})
        else:
            return jsonify({"error": "Failed to update log entry"}), 500


@app.route("/events", methods=["GET"])
def events():
    """
    Fetch upcoming community events for dashboard display.
    
    Query Parameters:
    - limit: Number of events to return (default 10)
    - days_ahead: How many days ahead to look (default 7)
    
    Response JSON:
    {
        "events": [...],
        "total": 5
    }
    """
    limit = request.args.get("limit", 10, type=int)
    days_ahead = request.args.get("days_ahead", 7, type=int)
    
    # Clamp values
    limit = max(1, min(limit, 100))
    days_ahead = max(1, min(days_ahead, 30))
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Build query using actual weekly_events table columns
        query = """
            SELECT 
                id, event_name, event_date, start_date, end_date, 
                start_time, end_time, raw_text, source_pdf
            FROM weekly_events
            WHERE start_date >= CURDATE()
              AND start_date <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
            ORDER BY start_date ASC, start_time ASC 
            LIMIT %s
        """
        params = [days_ahead, limit]
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # Format events
        events_list = []
        for row in rows:
            event = {
                "id": row["id"],
                "event_name": row["event_name"],
                "event_date": row["event_date"],
                "start_date": str(row["start_date"]) if row["start_date"] else None,
                "end_date": str(row["end_date"]) if row["end_date"] else None,
                "start_time": str(row["start_time"]) if row["start_time"] else None,
                "end_time": str(row["end_time"]) if row["end_time"] else None,
                "description": row["raw_text"],
                "source": row["source_pdf"],
            }
            events_list.append(event)
        
        return jsonify({
            "events": events_list,
            "total": len(events_list),
        })
    
    except Exception as e:
        print(f"Error in /events: {e}")
        return jsonify({"error": f"Failed to fetch events: {str(e)}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    status = {"status": "ok", "version": Config.API_VERSION}
    
    # Check database connection
    try:
        conn = get_db_connection()
        conn.close()
        status["database"] = "connected"
    except Exception:
        status["database"] = "disconnected"
        status["status"] = "degraded"
    
    return jsonify(status)


# =============================================================================
# Main Entry Point
# =============================================================================
if __name__ == "__main__":
    # Bootstrap environment
    _bootstrap_env()
    _fix_retrieval_vectordb_path()
    
    # Ensure database tables exist
    ensure_interaction_log_table()
    
    print(f"\n🚀 Agent API {Config.API_VERSION}")
    print(f"   Host: {Config.HOST}:{Config.PORT}")
    print(f"   Auth: {'Enabled' if Config.RETHINKAI_API_KEYS else 'Disabled'}")
    print()
    
    app.run(host=Config.HOST, port=Config.PORT, debug=True)

