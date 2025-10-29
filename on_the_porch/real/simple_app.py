import os
import json
import re
from typing import Callable
from pathlib import Path
from typing import Any, Dict, List

import pymysql
import sys


def _load_local_env() -> None:
    """Load .env from the same directory if present (no external deps)."""
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
        # Silently ignore .env parsing issues and rely on process env
        pass


_load_local_env()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", OPENAI_MODEL)

# Optional LangSmith tracing
try:
    from langsmith import traceable  # type: ignore
except Exception:
    def traceable(func: Callable):  # type: ignore
        return func


def _langsmith_enabled() -> bool:
    v = os.getenv("LANGCHAIN_TRACING_V2", "").strip().lower()
    return v in ("true", "1", "yes") and bool(os.getenv("LANGCHAIN_API_KEY"))


def _print_langsmith_banner() -> None:
    if _langsmith_enabled():
        project = os.getenv("LANGCHAIN_PROJECT", "default")
        print(f"LangSmith tracing enabled (project={project})")


def _get_db_connection():
    host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    port = int(os.environ.get("MYSQL_PORT", "3306"))
    user = os.environ.get("MYSQL_USER", "root")
    password = os.environ.get("MYSQL_PASSWORD", "")
    database = os.environ.get("MYSQL_DATABASE", "app")

    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4",
            autocommit=True,
        )
    except Exception as exc:
        print(f"DB connection failed: {exc}", file=sys.stderr)
        sys.exit(1)

    return conn


def _fetch_schema_snapshot(database: str) -> str:
    """Return a compact schema description (tables and columns)."""
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY TABLE_NAME, ORDINAL_POSITION
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


def _extract_sql_from_text(text: str) -> str:
    t = text.strip()
    # Prefer fenced code blocks and support optional language tag like ```sql
    m = re.search(r"```[ \t]*(?:sql|mysql)?[ \t]*\n([\s\S]*?)```", t, flags=re.IGNORECASE)
    if m:
        content = m.group(1).strip()
    else:
        m2 = re.search(r"```([\s\S]*?)```", t)
        if m2:
            content = m2.group(1).strip()
        else:
            content = t

    # If first line is just a language tag, drop it
    lines = content.splitlines()
    if lines and lines[0].strip().lower() in ("sql", "mysql"):
        content = "\n".join(lines[1:]).strip()
    return content


def _read_metadata_text() -> str:
    """Read optional metadata JSON from SCHEMA_METADATA_PATH and pretty-print it."""
    path = os.getenv("SCHEMA_METADATA_PATH")
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Pretty-print JSON to offer structure to the model
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"Warning: could not read metadata JSON: {exc}", file=sys.stderr)
        return ""


@traceable(name="generate_sql")
def _llm_generate_sql(question: str, schema: str, default_model: str, metadata: str = "") -> str:
    system_prompt = (
        "You are a helpful data analyst. Generate a single, syntactically correct MySQL "
        "SELECT statement based strictly on the provided schema. Do not include explanations. "
        "Only output SQL. Use table and column names exactly as shown."
    )

    if metadata:
        user_prompt = (
            "Schema:\n" + schema + "\n\n"
            "Additional metadata (JSON):\n" + metadata + "\n\n"
            "Instruction: Write a single MySQL SELECT to answer the question. "
            "If the question is ambiguous, choose a reasonable interpretation.\n\n"
            f"Question: {question}"
        )
    else:
        user_prompt = (
            "Schema:\n" + schema + "\n\n"
            "Instruction: Write a single MySQL SELECT to answer the question. "
            "If the question is ambiguous, choose a reasonable interpretation.\n\n"
            f"Question: {question}"
        )

    content = None

    # Try modern OpenAI client first, then fallback to legacy
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=OPENAI_API_KEY or None)
        resp = client.chat.completions.create(
            model=default_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
    except Exception:
        try:
            import openai  # type: ignore

            if OPENAI_API_KEY:
                openai.api_key = OPENAI_API_KEY
            resp = openai.ChatCompletion.create(
                model=default_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
            )
            content = resp["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            print(f"OpenAI error: {exc}", file=sys.stderr)
            sys.exit(1)

    sql_text = _extract_sql_from_text(content)
    return sql_text


@traceable(name="execute_sql")
def _execute_sql(sql: str) -> Dict[str, Any]:
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
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


@traceable(name="summarize_answer")
def _llm_generate_answer(question: str, sql: str, result: Dict[str, Any], default_model: str) -> str:
    cols = result.get("columns", [])
    rows = result.get("rows", [])
    if not rows:
        return "No results found."

    # Limit rows included in prompt to control tokens
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
    )

    user_prompt = (
        "Question:\n" + question + "\n\n"
        "Executed SQL:\n" + sql + "\n\n"
        "Result (JSON, possibly truncated):\n" + json.dumps(data_blob, ensure_ascii=False)
    )

    content = None
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=OPENAI_API_KEY or None)
        resp = client.chat.completions.create(
            model=default_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
    except Exception:
        try:
            import openai  # type: ignore

            if OPENAI_API_KEY:
                openai.api_key = OPENAI_API_KEY
            resp = openai.ChatCompletion.create(
                model=default_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
            )
            content = resp["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            # Fall back to simple textual rendering on failure
            header = ", ".join(cols)
            lines = [header] + [", ".join(str(r.get(c, "")) for c in cols) for r in sample_rows]
            if len(rows) > max_rows:
                lines.append(f"... ({len(rows) - max_rows} more rows)")
            return "\n".join(lines)

    return content.strip()
def _print_schema(database: str) -> None:
    print("=== Database schema (tables/columns) ===")
    print(_fetch_schema_snapshot(database))


def _interactive_loop() -> None:
    if not (OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")):
        print("OPENAI_API_KEY not configured", file=sys.stderr)
        sys.exit(1)

    database = os.environ.get("MYSQL_DATABASE", "app")
    _print_langsmith_banner()
    metadata = _read_metadata_text()
    _print_schema(database)

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

        sql = _llm_generate_sql(
            prompt,
            _fetch_schema_snapshot(database),
            OPENAI_MODEL,
            metadata,
        )
        print("\n[SQL]\n" + sql + "\n")
        try:
            result = _execute_sql(sql)
        except Exception as exc:
            print(f"Execution error: {exc}")
            continue

        answer = _llm_generate_answer(prompt, sql, result, OPENAI_SUMMARY_MODEL)
        print("[Answer]\n" + answer + "\n")


def main() -> None:
    if len(sys.argv) > 1:
        # One-shot mode: python real/simple_app.py "your question here"
        question = " ".join(sys.argv[1:])
        database = os.environ.get("MYSQL_DATABASE", "app")
        schema = _fetch_schema_snapshot(database)
        metadata = _read_metadata_text()
        _print_langsmith_banner()
        sql = _llm_generate_sql(question, schema, OPENAI_MODEL, metadata)
        print(sql)
        result = _execute_sql(sql)
        answer = _llm_generate_answer(question, sql, result, OPENAI_SUMMARY_MODEL)
        print(answer)
    else:
        _interactive_loop()


if __name__ == "__main__":
    main()


