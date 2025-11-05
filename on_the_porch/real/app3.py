import os
import sys
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Callable

import psycopg2
from pocketflow import Flow, Node
from openai import OpenAI  # type: ignore
try:
    from langsmith.wrappers import wrap_openai  # type: ignore
except Exception:
    def wrap_openai(client):
        return client


def _load_local_env() -> None:
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


_load_local_env()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", OPENAI_MODEL)
SQL_MAX_RETRIES = int(os.getenv("SQL_MAX_RETRIES", "2"))  # Reduced default to 2 for faster execution

# Optional LangSmith tracing
try:
    from langsmith import traceable  # type: ignore
except Exception:
    def traceable(func: Callable):  # type: ignore
        return func


def _langsmith_enabled() -> bool:
    v1 = os.getenv("LANGCHAIN_TRACING_V2", "").strip().lower()
    v2 = os.getenv("LANGSMITH_TRACING", "").strip().lower()
    enabled = (v1 in ("true", "1", "yes")) or (v2 in ("true", "1", "yes"))
    return enabled and bool(os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY"))


def _print_langsmith_banner() -> None:
    if _langsmith_enabled():
        project = os.getenv("LANGCHAIN_PROJECT", os.getenv("LANGSMITH_PROJECT", "default"))
        print(f"LangSmith tracing enabled (project={project})")


def _get_openai_client() -> OpenAI:
    client = OpenAI(api_key=OPENAI_API_KEY or None, timeout=60)
    return wrap_openai(client)


def _get_db_connection():
    # Require DATABASE_URL from environment/.env
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set in environment (.env)", file=sys.stderr)
        sys.exit(1)

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
    except Exception as exc:
        print(f"DB connection failed: {exc}", file=sys.stderr)
        sys.exit(1)

    return conn


def _fetch_schema_snapshot(database: str) -> str:
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                (database,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    table_to_columns: Dict[str, List[str]] = {}
    for table_name, column_name in rows:
        table_to_columns.setdefault(table_name, []).append(column_name)

    lines: List[str] = []
    for table_name, columns in table_to_columns.items():
        lines.append(f"{table_name} (" + ", ".join(columns) + ")")
    return "\n".join(lines) if lines else "(no tables)"


def _get_unique_values(table_name: str, column_name: str, schema: str = "public", limit: int = 50) -> List[Any]:
    """Get unique values from a column to help users see available options."""
    conn = _get_db_connection()
    try:
        # Set a statement timeout to prevent hanging (5 seconds)
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '5s'")
            cur.execute(
                f'''
                SELECT DISTINCT "{column_name}"
                FROM "{schema}"."{table_name}"
                WHERE "{column_name}" IS NOT NULL
                ORDER BY "{column_name}"
                LIMIT %s
                ''',
                (limit,),
            )
            rows = cur.fetchall()
            return [row[0] for row in rows]
    except Exception as exc:
        # If query times out or fails, return empty list
        print(f"[Warning] Could not fetch unique values for {table_name}.{column_name}: {exc}", file=sys.stderr)
        return []
    finally:
        conn.close()


def _get_table_columns_from_sql(sql: str, schema_snapshot: str) -> Dict[str, List[str]]:
    """Extract table and column names from SQL query to identify which columns to get unique values from."""
    import re
    # Simple extraction - look for table names in FROM/JOIN clauses
    table_cols: Dict[str, List[str]] = {}
    # Try to extract table name from FROM clause
    from_match = re.search(r'FROM\s+"?(\w+)"?\s+"?(\w+)"?', sql, re.IGNORECASE)
    if from_match:
        schema_part = from_match.group(1)
        table_name = from_match.group(2) if from_match.group(2) else from_match.group(1)
        # Look for this table in schema snapshot
        table_pattern = rf'{table_name}\s*\([^)]+\)'
        match = re.search(table_pattern, schema_snapshot, re.IGNORECASE)
        if match:
            cols_str = match.group(0)
            cols_match = re.search(r'\(([^)]+)\)', cols_str)
            if cols_match:
                cols = [c.strip().strip('"') for c in cols_match.group(1).split(',')]
                table_cols[table_name] = cols
    return table_cols


def _extract_sql_from_text(text: str) -> str:
    t = text.strip()
    m = re.search(r"```[ \t]*(?:sql|mysql)?[ \t]*\n([\s\S]*?)```", t, flags=re.IGNORECASE)
    if m:
        content = m.group(1).strip()
    else:
        m2 = re.search(r"```([\s\S]*?)```", t)
        if m2:
            content = m2.group(1).strip()
        else:
            content = t
    lines = content.splitlines()
    if lines and lines[0].strip().lower() in ("sql", "mysql"):
        content = "\n".join(lines[1:]).strip()
    return content


def _read_metadata_text() -> str:
    path = os.getenv("SCHEMA_METADATA_PATH")
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"Warning: could not read metadata JSON: {exc}", file=sys.stderr)
        return ""


def _load_catalog_entries() -> List[Dict[str, Any]]:
    """Load tables catalog from METADATA_CATALOG_PATH or default location."""
    default_path = Path(__file__).resolve().parents[1] / "meta data" / "tables_catalog.json"
    path = os.getenv("METADATA_CATALOG_PATH", str(default_path))
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict) and "table" in x]
    except Exception:
        pass
    return []


def _llm_select_tables(question: str, catalog: List[Dict[str, Any]], default_model: str) -> List[str]:
    if not catalog:
        return []

    brief_rows = [
        {"table": c.get("table"), "description": c.get("description", "")}
        for c in catalog
        if isinstance(c, dict) and c.get("table")
    ]

    system_prompt = (
        "You are a helpful data analyst. Given a user question and a list of tables with "
        "brief descriptions, choose the minimal set of tables whose metadata would be most "
        "useful to correctly write SQL. Output strictly a JSON array of table names. No text."
    )
    user_prompt = (
        "Question:\n" + question + "\n\n" +
        "Tables (JSON):\n" + json.dumps(brief_rows, ensure_ascii=False)
    )

    client = _get_openai_client()
    try:
        resp = client.chat.completions.create(
            model=default_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        content = (resp.choices[0].message.content or "").strip()
    except Exception:
        return []

    # Try to extract JSON array of strings
    try:
        # Remove code fences if present
        m = re.search(r"```[\s\S]*?```", content)
        if m:
            inner = m.group(0)
            content = re.sub(r"^```[a-zA-Z]*\\n|```$", "", inner, flags=re.MULTILINE).strip()
        data = json.loads(content)
        if isinstance(data, list):
            names = [x for x in data if isinstance(x, str)]
        else:
            names = []
    except Exception:
        names = []

    available = {c.get("table"): c for c in catalog if isinstance(c, dict)}
    return [n for n in names if n in available]


def _read_selected_metadata_json(selected_tables: List[str], catalog: List[Dict[str, Any]]) -> str:
    if not selected_tables:
        return ""
    default_dir = Path(__file__).resolve().parents[1] / "meta data"
    base_dir = Path(os.getenv("METADATA_DIR", str(default_dir)))
    table_to_entry = {c.get("table"): c for c in catalog if isinstance(c, dict) and c.get("table")}

    result: Dict[str, Any] = {"tables": []}
    for table in selected_tables:
        entry = table_to_entry.get(table)
        if not entry:
            continue
        fname = entry.get("metadata_file")
        if not fname:
            continue
        fpath = base_dir / fname
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                meta_json = json.load(f)
            result["tables"].append({"table": table, "metadata": meta_json})
        except Exception:
            # Skip unreadable files
            continue
    try:
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception:
        return ""


def _build_question_metadata(question: str) -> str:
    catalog = _load_catalog_entries()
    if not catalog:
        return _read_metadata_text()
    tables = _llm_select_tables(question, catalog, OPENAI_MODEL)
    meta = _read_selected_metadata_json(tables, catalog)
    return meta or _read_metadata_text()


@traceable(name="generate_sql")
def _llm_generate_sql(question: str, schema: str, default_model: str, metadata: str = "", conversation_history: List[Dict[str, str]] | None = None) -> str:
    system_prompt = (
        "You are a helpful data analyst. Generate a single, syntactically correct PostgreSQL "
        "SELECT statement based strictly on the provided schema snapshot and optional metadata JSON. "
        "Do not include explanations. Only output SQL.\n\n"
        "Rules:\n"
        "- USE ONLY tables and columns present in the schema snapshot; DO NOT invent new names (e.g., never create \"street_violations\").\n"
        "- If metadata indicates certain columns are UNIQUE/identifiers (e.g., primary keys or constrained categories), prefer those columns for exact filtering, grouping, or joining.\n"
        "- Prefer columns indicated in metadata (JSON) when filtering (e.g., request_type, category, subject, description).\n"
        "- When the question uses non-schema phrases (e.g., \"street violations\"), map them to appropriate text/category columns and use case-insensitive matches (ILIKE) rather than fabricating table names.\n"
        "- For 311 tables (\"service_requests\" or \"dorchester_311\"): use \"type\" or \"reason\" for category/topic filtering; avoid using \"subject\" (department) for problem categories.\n"
        "- For police offenses (\"offenses\"): map \"violation\" terms to the \"Crime\" field (e.g., 'LICENSE VIOLATION', 'VIOLATIONS') using ILIKE when appropriate.\n"
        "- IMPORTANT: Do NOT search generically for the literal word 'violation' (e.g., avoid WHERE col ILIKE '%violation%'). Instead, select concrete categories/values from the appropriate columns (e.g., specific 311 'type'/'reason' values, or explicit 'Crime' values such as 'LICENSE VIOLATION').\n"
        "- Type correctness: NEVER compare text to timestamps. If a date/time column is text per metadata (e.g., 'open_dt' in 'dorchester_311'), CAST it to timestamp (e.g., \"open_dt\"::timestamp) before comparing to NOW() or intervals.\n"
        "- If metadata.hints.need_location is true and the selected table includes latitude/longitude columns (e.g., 'latitude', 'longitude'), INCLUDE them in the SELECT. If returning many rows, LIMIT to a reasonable sample (e.g., 500).\n"
        "- If metadata.hints.prefer_location is true, strongly consider including latitude/longitude columns in the SELECT when available, especially for questions about locations, places, neighborhoods, or showing/visualizing data.\n"
        "- For queries involving 'where', 'location', 'show', 'find', 'map', or spatial concepts, ALWAYS include latitude and longitude columns when available in the table schema.\n"
        "- ALWAYS wrap schema, table, and column identifiers in double quotes."
    )

    if metadata:
        user_prompt = (
            "Schema:\n" + schema + "\n\n"
            "Additional metadata (JSON):\n" + metadata + "\n\n"
            "Instruction: Write a single PostgreSQL SELECT to answer the question. "
            "Always double-quote all identifiers (schema, table, column). "
            "If the question is ambiguous, choose a reasonable interpretation.\n\n"
            f"Question: {question}"
        )
    else:
        user_prompt = (
            "Schema:\n" + schema + "\n\n"
            "Instruction: Write a single PostgreSQL SELECT to answer the question. "
            "Always double-quote all identifiers (schema, table, column). "
            "If the question is ambiguous, choose a reasonable interpretation.\n\n"
            f"Question: {question}"
        )

    if conversation_history:
        # Add note about conversation context
        system_prompt += "\n\nNote: You are in a conversation. If the question references previous context, use it to better understand what the user is asking."
    
    messages = [{"role": "system", "content": system_prompt}]
    if conversation_history:
        # Add conversation history (last 8 exchanges to keep within token limits for SQL generation)
        messages.extend(conversation_history[-8:])
    messages.append({"role": "user", "content": user_prompt})

    client = _get_openai_client()
    try:
        resp = client.chat.completions.create(
            model=default_model,
            messages=messages,
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
        return _extract_sql_from_text(content)
    except Exception as exc:
        raise RuntimeError(f"OpenAI error: {exc}")


@traceable(name="refine_sql_on_error")
def _llm_refine_sql(
    question: str,
    schema: str,
    previous_sql: str,
    error_text: str,
    default_model: str,
    metadata: str = "",
) -> str:
    # Always rebuild metadata if not provided to ensure we have table information
    if not metadata:
        metadata = _build_question_metadata(question)
    
    # Parse error to extract key information
    error_lower = error_text.lower()
    missing_column = None
    if "does not exist" in error_lower:
        # Try to extract column name from error
        col_match = re.search(r'column\s+"([^"]+)"\s+does not exist|column\s+(\w+)\s+does not exist', error_lower, re.IGNORECASE)
        if col_match:
            missing_column = col_match.group(1) or col_match.group(2)
    
    system_prompt = (
        "You are a helpful data analyst. Given a PostgreSQL error, the schema snapshot, and metadata JSON, "
        "correct the SQL so it runs successfully. Output only a single PostgreSQL SELECT statement with no explanations.\n\n"
        "CRITICAL RULES:\n"
        "- USE ONLY tables/columns present in the schema snapshot; DO NOT invent names.\n"
        "- If the error mentions a column that 'does not exist', REMOVE that column from the SELECT statement immediately.\n"
        "- ALWAYS check the schema snapshot to verify which columns actually exist before using them.\n"
        "- If metadata marks certain columns as UNIQUE/identifiers, prefer those for exact filters/joins instead of free-text conditions.\n"
        "- Prefer text/category columns identified in metadata for filtering ambiguous phrases (use ILIKE).\n"
        "- For 311 tables (\"service_requests\" or \"dorchester_311\"): prefer filtering on \"type\" or \"reason\" for categories; avoid \"subject\" when searching for problem types.\n"
        "- For police offenses (\"offenses\"): consider \"Crime\" values like 'LICENSE VIOLATION' or 'VIOLATIONS' when the user mentions violations.\n"
        "- Type correctness: If the error indicates comparing text to timestamp (e.g., 'operator does not exist: text >= timestamp with time zone'), CAST text date columns to timestamp (\"col\"::timestamp) before date math.\n"
        "- If metadata.hints.need_location is true and coordinates exist, INCLUDE latitude/longitude in the SELECT and consider applying a LIMIT (e.g., 500).\n"
        "- IMPORTANT: Do NOT use a generic ILIKE '%violation%' filter. Choose specific, valid category/value filters instead.\n"
        "- ALWAYS wrap identifiers (schema, table, column) in double quotes."
    )
    
    # Build enhanced error analysis
    error_analysis = f"Error: {error_text}"
    if missing_column:
        error_analysis += f"\n\nANALYSIS: The column '{missing_column}' does not exist in the table. Remove it from the SELECT statement and use only columns listed in the schema snapshot above."
    
    user_prompt = (
        "Schema (shows all available tables and columns):\n" + schema + "\n\n"
        "Metadata (JSON) for tables:\n" + (metadata if metadata else "{}") + "\n\n"
        "Question:\n" + question + "\n\n"
        "Previous SQL (has errors):\n```sql\n" + previous_sql + "\n```\n\n"
        "PostgreSQL Error:\n" + error_analysis + "\n\n"
        "Instruction: Provide a corrected single PostgreSQL SELECT statement that resolves the error. "
        "Only use columns that exist in the schema snapshot. Always double-quote all identifiers (schema, table, column)."
    )

    client = _get_openai_client()
    resp = client.chat.completions.create(
        model=default_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    content = resp.choices[0].message.content or ""
    return _extract_sql_from_text(content)


@traceable(name="execute_sql")
def _execute_sql(sql: str) -> Dict[str, Any]:
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            # Set statement timeout to prevent hanging (30 seconds)
            cur.execute("SET statement_timeout = '30s'")
            cur.execute(sql)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
    finally:
        conn.close()

    items: List[Dict[str, Any]] = []
    for row in rows:
        item = {cols[i]: row[i] for i in range(len(cols))}
        items.append(item)
    return {"columns": cols, "rows": items}


@traceable(name="execute_with_retries")
def _execute_with_retries(
    initial_sql: str,
    question: str,
    schema: str,
    metadata: str,
    max_attempts: int = SQL_MAX_RETRIES,
) -> Dict[str, Any]:
    # Clamp max attempts to prevent infinite loops
    max_attempts = max(1, min(int(max_attempts or 1), 5))
    sql = initial_sql
    last_err: Exception | None = None
    previous_sqls = []  # Track previous SQL attempts to avoid infinite loops
    error_count = {}  # Track how many times we've seen the same error
    
    for attempt_idx in range(1, max_attempts + 1):
        try:
            if attempt_idx == 1:
                print("\n[SQL]\n" + sql + "\n")
            else:
                print(f"\n[SQL Retry {attempt_idx - 1}]\n" + sql + "\n")
            
            # Normalize SQL for comparison (remove extra whitespace)
            sql_normalized = " ".join(sql.split())
            if sql_normalized in previous_sqls:
                # Same SQL as before - avoid infinite loop, return early
                print(f"\n[Warning] SQL same as previous attempt, stopping to avoid infinite loop\n")
                result = {"columns": [], "rows": []}
                return {"result": result, "sql": sql}
            
            previous_sqls.append(sql_normalized)
            
            result = _execute_sql(sql)
            # If query succeeded but returned no rows, try to refine and broaden the query
            try:
                rows = result.get("rows", []) if isinstance(result, dict) else []
            except Exception:
                rows = []
            if rows:
                return {"result": result, "sql": sql}
            
            # No rows returned - gather unique values from key columns to help user
            # Skip this if we're on attempt 2+ to speed things up
            unique_values_info = {}
            if attempt_idx == 1:  # Only fetch unique values on first attempt
                try:
                    # Extract table and key columns from SQL and schema
                    import re
                    table_name = None
                    schema_name = os.environ.get("PGSCHEMA", "public")
                    
                    # Find table name from FROM clause - handle schema.table format
                    from_match = re.search(r'FROM\s+"([^"]+)"\s*\.\s*"([^"]+)"|FROM\s+"([^"]+)"', sql, re.IGNORECASE)
                    if from_match:
                        if from_match.group(2):  # schema.table format
                            schema_name = from_match.group(1).strip('"').strip()
                            table_name = from_match.group(2).strip('"').strip()
                        else:  # Just table name
                            table_name = from_match.group(3).strip('"').strip() if from_match.group(3) else from_match.group(1).strip('"').strip()
                    else:
                        # Try without quotes
                        from_match2 = re.search(r'FROM\s+(\w+)\.(\w+)|FROM\s+(\w+)', sql, re.IGNORECASE)
                        if from_match2:
                            if from_match2.group(2):  # schema.table format
                                schema_name = from_match2.group(1)
                                table_name = from_match2.group(2)
                            else:  # Just table name
                                table_name = from_match2.group(3) or from_match2.group(1)
                    
                    if table_name:
                        # Try to find key category/type columns from schema
                        schema_lines = schema.split('\n')
                        key_columns = []
                        for line in schema_lines:
                            if table_name.lower() in line.lower():
                                # Extract column names from this table's line
                                cols_match = re.search(r'\(([^)]+)\)', line)
                                if cols_match:
                                    cols = [c.strip().strip('"') for c in cols_match.group(1).split(',')]
                                    # Prioritize common category/type columns
                                    for col in cols:
                                        col_lower = col.lower()
                                        if any(kw in col_lower for kw in ['type', 'reason', 'category', 'subject', 'crime', 'status', 'state']):
                                            key_columns.append(col)
                                    # If no specific columns found, take first few columns
                                    if not key_columns and cols:
                                        key_columns = cols[:3]
                        
                        # Get unique values from these columns (limit to 2 columns and 10 values each to speed up)
                        for col in key_columns[:2]:  # Limit to 2 columns
                            try:
                                unique_vals = _get_unique_values(table_name, col, schema_name, limit=10)
                                if unique_vals:
                                    unique_values_info[col] = unique_vals
                            except Exception:
                                pass
                except Exception:
                    pass
            
            # Add unique values to result for display
            if unique_values_info:
                result["unique_values"] = unique_values_info
                result["no_rows_with_suggestions"] = True
            
            # No rows; refine unless at last attempt
            if attempt_idx == max_attempts:
                return {"result": result, "sql": sql}
            
            # On second attempt with no rows, return early to avoid expensive retries
            if attempt_idx >= 2:
                print(f"\n[Info] After {attempt_idx} attempts with no rows, stopping to avoid delays\n")
                return {"result": result, "sql": sql}
            
            # Build error text with unique values info (only on first retry)
            error_parts = [
                "No rows returned. Broaden or correct filters based on metadata: "
                "For 311 tables use \"type\"/\"reason\" categories (avoid \"subject\"), "
                "and use ILIKE for ambiguous phrases. For \"offenses\", consider \"Crime\" values "
                "like 'LICENSE VIOLATION'/'VIOLATIONS'."
            ]
            if unique_values_info:
                error_parts.append("\n\nAvailable values in key columns:")
                for col, vals in unique_values_info.items():
                    error_parts.append(f"  - {col}: {', '.join(str(v)[:50] for v in vals[:10])}{'...' if len(vals) > 10 else ''}")
                error_parts.append("\nConsider using these actual values from the database in your filters.")
            
            # Always ensure metadata is available
            current_metadata = metadata if metadata else _build_question_metadata(question)
            
            sql = _llm_refine_sql(
                question=question,
                schema=schema,
                previous_sql=sql or "",
                error_text="\n".join(error_parts),
                default_model=OPENAI_MODEL,
                metadata=current_metadata,
            )
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt_idx == max_attempts:
                raise
            
            err_text = str(exc)
            
            # Track error patterns to detect loops
            error_key = err_text[:200]  # Use first 200 chars as key
            error_count[error_key] = error_count.get(error_key, 0) + 1
            
            # If we've seen this exact error 2+ times, stop to avoid infinite loop
            if error_count[error_key] >= 2:
                print(f"\n[Warning] Same error repeated {error_count[error_key]} times, stopping to avoid infinite loop\n")
                result = {"columns": [], "rows": []}
                return {"result": result, "sql": sql}
            
            try:
                # Augment certain common type errors with guidance
                if "operator does not exist: text" in err_text and "timestamp" in err_text:
                    err_text += (
                        "\nHint: CAST text date columns to timestamp (e.g., \"open_dt\"::timestamp) "
                        "before comparing to NOW() or using intervals."
                    )
                
                # Always rebuild metadata to ensure we have latest table info
                current_metadata = metadata if metadata else _build_question_metadata(question)
                
                sql = _llm_refine_sql(
                    question=question,
                    schema=schema,
                    previous_sql=sql or "",
                    error_text=err_text,
                    default_model=OPENAI_MODEL,
                    metadata=current_metadata,
                )
            except Exception as refine_exc:  # noqa: BLE001
                last_err = refine_exc
                # If refinement itself fails, stop after 2 attempts
                if attempt_idx >= 2:
                    raise
                continue
    # Should not reach here; re-raise last error if loop exits unexpectedly
    if last_err:
        raise last_err
    raise RuntimeError("Unknown error during SQL execution with retries")


@traceable(name="summarize_answer")
def _llm_generate_answer(question: str, sql: str, result: Dict[str, Any], default_model: str, conversation_history: List[Dict[str, str]] | None = None) -> str:
    cols = result.get("columns", [])
    rows = result.get("rows", [])
    if not rows:
        unique_values = result.get("unique_values", {})
        if unique_values:
            # Build a helpful message with unique values
            msg_parts = ["No results found matching your query."]
            msg_parts.append("\n\nTo help refine your search, here are available values in key columns:")
            for col, vals in list(unique_values.items())[:3]:  # Limit to 3 columns
                sample_vals = vals[:10]  # Show first 10 values
                vals_str = ", ".join(str(v)[:50] for v in sample_vals)
                if len(vals) > 10:
                    vals_str += f" (and {len(vals) - 10} more)"
                msg_parts.append(f"\n- **{col}**: {vals_str}")
            msg_parts.append("\n\nTry using one of these actual values from the database in your question.")
            return "".join(msg_parts)
        return "No results found."

    max_rows = 30
    sample_rows = rows[:max_rows]
    data_blob = {
        "columns": cols,
        "rows": sample_rows,
        "truncated": len(rows) > max_rows,
        "row_count": len(rows),
    }

    system_prompt = (
        "You are a data assistant. Provide a concise, human-readable answer based on the "
        "SQL result. If it is an aggregation, report key figures clearly. If it is tabular, "
        "briefly summarize notable rows or totals. Do not include SQL in the answer."
        + ("\n\nYou are in a conversation. Reference previous context naturally when the question relates to earlier topics." if conversation_history else "")
    )

    user_prompt = (
        "Question:\n" + question + "\n\n"
        "Executed SQL:\n" + sql + "\n\n"
        "Result (JSON, possibly truncated):\n" + json.dumps(data_blob, ensure_ascii=False, default=str)
    )

    messages = [{"role": "system", "content": system_prompt}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({"role": "user", "content": user_prompt})

    client = _get_openai_client()
    try:
        resp = client.chat.completions.create(
            model=default_model,
            messages=messages,
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
        return content.strip()
    except Exception:
        header = ", ".join(cols)
        lines = [header] + [", ".join(str(r.get(c, "")) for c in cols) for r in sample_rows]
        if len(rows) > max_rows:
            lines.append(f"... ({len(rows) - max_rows} more rows)")
        return "\n".join(lines)


def _print_schema(database: str) -> None:
    print("=== Database schema (tables/columns) ===")
    print(_fetch_schema_snapshot(database))


# Pretty-print a sample of the SQL result rows
def _print_result(result: Dict[str, Any]) -> None:
    try:
        cols = result.get("columns", []) if isinstance(result, dict) else []
        rows = result.get("rows", []) if isinstance(result, dict) else []
        print("[Result] rows=", len(rows))
        if not cols or not rows:
            return
        header = " | ".join(str(c) for c in cols)
        print(header)
        print("-" * len(header))
        max_rows = 30
        for r in rows[:max_rows]:
            line = " | ".join(str(r.get(c, "")) for c in cols)
            print(line)
        if len(rows) > max_rows:
            print(f"... ({len(rows) - max_rows} more rows)")
    except Exception:
        try:
            print(json.dumps(result, ensure_ascii=False, default=str)[:4000])
        except Exception:
            pass


# Pocketflow Nodes
class GetSchemaNode(Node):
    def prep(self, shared):
        return shared.get("database")

    def exec(self, database):
        return _fetch_schema_snapshot(database)

    def post(self, shared, prep_res, exec_res):
        shared["schema"] = exec_res
        return "default"


class GenerateSQLNode(Node):
    def prep(self, shared):
        return {
            "question": shared.get("question"),
            "schema": shared.get("schema"),
            "metadata": shared.get("metadata", ""),
        }

    def exec(self, prep_res):
        return _llm_generate_sql(prep_res["question"], prep_res["schema"], OPENAI_MODEL, prep_res["metadata"])

    def post(self, shared, prep_res, exec_res):
        shared["sql"] = exec_res
        print("\n[SQL]\n" + exec_res + "\n")
        return "default"


class RunSQLNode(Node):
    def prep(self, shared):
        return {
            "sql": shared.get("sql"),
            "question": shared.get("question"),
            "schema": shared.get("schema"),
            "metadata": shared.get("metadata", ""),
        }

    def exec(self, prep_res):
        return _execute_with_retries(
            initial_sql=prep_res["sql"],
            question=prep_res.get("question", ""),
            schema=prep_res.get("schema", ""),
            metadata=prep_res.get("metadata", ""),
        )

    def post(self, shared, prep_res, exec_res):
        shared["result"] = exec_res["result"]
        # Ensure shared SQL reflects the possibly refined SQL
        shared["sql"] = exec_res.get("sql", prep_res.get("sql"))
        _print_result(shared["result"])  # show SQL call return
        return "default"


class SummarizeNode(Node):
    def prep(self, shared):
        return {
            "question": shared.get("question"),
            "sql": shared.get("sql"),
            "result": shared.get("result"),
        }

    def exec(self, prep_res):
        return _llm_generate_answer(prep_res["question"], prep_res["sql"], prep_res["result"], OPENAI_SUMMARY_MODEL)

    def post(self, shared, prep_res, exec_res):
        shared["answer"] = exec_res
        print("[Answer]\n" + exec_res + "\n")
        return None


def _run_pipeline_fallback(shared: Dict[str, Any]) -> None:
    # Fallback: run steps sequentially without Pocketflow in case of flow incompatibility
    database = shared.get("database")
    question = shared.get("question")
    metadata = shared.get("metadata", "")

    schema = _fetch_schema_snapshot(database)
    shared["schema"] = schema
    sql = _llm_generate_sql(question, schema, OPENAI_MODEL, metadata)
    shared["sql"] = sql
    exec_out = _execute_with_retries(
        initial_sql=sql,
        question=question or "",
        schema=schema,
        metadata=metadata,
    )
    shared["sql"] = exec_out["sql"]
    shared["result"] = exec_out["result"]
    _print_result(shared["result"])  # show SQL call return (fallback)
    answer = _llm_generate_answer(question, shared["sql"], shared["result"], OPENAI_SUMMARY_MODEL)
    shared["answer"] = answer
    print("[Answer]\n" + answer + "\n", flush=True)


def _interactive_loop() -> None:
    if not (OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")):
        print("OPENAI_API_KEY not configured", file=sys.stderr)
        sys.exit(1)

    database = os.environ.get("PGSCHEMA", "public")
    _print_langsmith_banner()
    _print_schema(database)

    get_schema = GetSchemaNode()
    gen_sql = GenerateSQLNode()
    run_sql = RunSQLNode()
    summarize = SummarizeNode()

    flow = Flow().start(get_schema)
    get_schema >> gen_sql >> run_sql >> summarize

    print("\nType a question to query the database (or 'exit' to quit).\n")
    while True:
        try:
            prompt = input("Question> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not prompt:
            continue
        if prompt.lower() in {"exit", "quit", ":q", "q"}:
            break

        # Build metadata per-question from catalog selection
        metadata_blob = _build_question_metadata(prompt)
        shared = {"question": prompt, "database": database, "metadata": metadata_blob}
        try:
            # Support different pocketflow versions
            if hasattr(flow, "_run"):
                flow._run(shared)
            else:
                flow.run(shared)
        except Exception as exc:
            print(f"Error while running flow: {exc}", file=sys.stderr)
        # Fallback if no answer was produced
        if not shared.get("answer"):
            _run_pipeline_fallback(shared)


def main() -> None:
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        if not (OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")):
            print("OPENAI_API_KEY not configured", file=sys.stderr)
            sys.exit(1)

        database = os.environ.get("PGSCHEMA", "public")
        # Build metadata per-question from catalog selection
        metadata = _build_question_metadata(question)
        _print_langsmith_banner()

        get_schema = GetSchemaNode()
        gen_sql = GenerateSQLNode()
        run_sql = RunSQLNode()
        summarize = SummarizeNode()

        flow = Flow().start(get_schema)
        get_schema >> gen_sql >> run_sql >> summarize

        shared = {"question": question, "database": database, "metadata": metadata}
        try:
            if hasattr(flow, "_run"):
                flow._run(shared)
            else:
                flow.run(shared)
        except Exception as exc:
            print(f"Error while running flow: {exc}", file=sys.stderr)
        if not shared.get("answer"):
            _run_pipeline_fallback(shared)
    else:
        _interactive_loop()


if __name__ == "__main__":
    main()


