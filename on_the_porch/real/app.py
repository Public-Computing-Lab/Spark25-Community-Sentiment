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


@traceable(name="generate_sql")
def _llm_generate_sql(question: str, schema: str, default_model: str, metadata: str = "") -> str:
    system_prompt = (
        "You are a helpful data analyst. Generate a single, syntactically correct PostgreSQL "
        "SELECT statement based strictly on the provided schema. Do not include explanations. "
        "Only output SQL. Use table and column names exactly as shown."
    )

    if metadata:
        user_prompt = (
            "Schema:\n" + schema + "\n\n"
            "Additional metadata (JSON):\n" + metadata + "\n\n"
            "Instruction: Write a single PostgreSQL SELECT to answer the question. "
            "If the question is ambiguous, choose a reasonable interpretation.\n\n"
            f"Question: {question}"
        )
    else:
        user_prompt = (
            "Schema:\n" + schema + "\n\n"
            "Instruction: Write a single PostgreSQL SELECT to answer the question. "
            "If the question is ambiguous, choose a reasonable interpretation.\n\n"
            f"Question: {question}"
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
        content = resp.choices[0].message.content or ""
        return _extract_sql_from_text(content)
    except Exception as exc:
        raise RuntimeError(f"OpenAI error: {exc}")


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
        "Result (JSON, possibly truncated):\n" + json.dumps(data_blob, ensure_ascii=False, default=str)
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
        return shared.get("sql")

    def exec(self, sql):
        return _execute_sql(sql)

    def post(self, shared, prep_res, exec_res):
        shared["result"] = exec_res
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
    print("\n[SQL]\n" + sql + "\n", flush=True)
    result = _execute_sql(sql)
    shared["result"] = result
    answer = _llm_generate_answer(question, sql, result, OPENAI_SUMMARY_MODEL)
    shared["answer"] = answer
    print("[Answer]\n" + answer + "\n", flush=True)


def _interactive_loop() -> None:
    if not (OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")):
        print("OPENAI_API_KEY not configured", file=sys.stderr)
        sys.exit(1)

    database = os.environ.get("PGSCHEMA", "public")
    metadata = _read_metadata_text()
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

        shared = {"question": prompt, "database": database, "metadata": metadata}
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
        metadata = _read_metadata_text()
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
