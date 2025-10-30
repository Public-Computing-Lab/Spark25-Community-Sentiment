import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Ensure we can import RAG utilities from the directory with a space in its name
_THIS_FILE = Path(__file__).resolve()
_REAL_DIR = _THIS_FILE.parent
_ROOT_DIR = _REAL_DIR.parent.parent
_RAG_DIR = _REAL_DIR.parent / "rag stuff"
if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))


# Import RAG retrieval helpers; import SQL pipeline lazily only when needed
import retrieval  # type: ignore  # noqa: E402

# Local OpenAI client config (avoid importing app3 at module load)
try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", OPENAI_MODEL)


def _bootstrap_env() -> None:
    # Load .env in this directory if present
    env_path = _REAL_DIR / ".env"
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


def _fix_retrieval_vectordb_path() -> None:
    # retrieval.VECTORDB_DIR is relative; ensure it points to on_the_porch/vectordb_new
    try:
        expected = _REAL_DIR.parent / "vectordb_new"
        retrieval.VECTORDB_DIR = expected  # type: ignore[attr-defined]
    except Exception:
        pass


def _get_llm_client():
    if OpenAI is None:
        raise RuntimeError("openai client not installed: pip install openai")
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY") or None, timeout=60)


def _safe_json_loads(text: str, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        return default


def _route_question(question: str) -> Dict[str, Any]:
    """
    Decide whether to answer via SQL, RAG, or HYBRID.
    Returns a dict like: {"mode": "sql|rag|hybrid", "transcript_tags": [..]|null, "policy_sources": [..]|null, "k": int}
    """
    # Lightweight heuristic: direct SQL for clearly quantitative queries
    quantitative_phrases = [
        "how many", "count", "counts", "number of", "avg", "average", "sum", "total",
        "trend", "per year", "by year", "by month", "top", "rank", "distribution",
        "percent", "percentage", "ratio", "rate", "compare", "comparison",
    ]
    q_lower = (question or "").lower()
    if any(p in q_lower for p in quantitative_phrases):
        return {"mode": "sql", "transcript_tags": None, "policy_sources": None, "k": 3}

    client = _get_llm_client()

    system_prompt = (
        "You are a routing classifier for a chatbot that combines SQL (structured data) and RAG (text documents).\n"
        "Classify the user's question into one of three modes: 'sql', 'rag', or 'hybrid'. If uncertain, choose 'rag'.\n\n"
        "Use the following logic with examples grounded in our data:\n"
        "- 'sql': for statistics, counts, trends, comparisons, numeric breakdowns from Postgres tables like\n"
        "  'service_requests' (311), 'arrests', 'offenses', 'homicides', 'shots_fired', or Dorchester-focused tables.\n"
        "  Examples: 'How many 311 service requests were filed in Dorchester last month?',\n"
        "  'What is the trend in shots fired by year in Boston?',\n"
        "  'Which neighborhoods have the highest arrests in 2023?'\n"
        "- 'rag': for qualitative, descriptive, or policy questions answered by documents/transcripts, such as\n"
        "  'Boston Anti-Displacement Plan Analysis.txt', 'Boston Slow Streets Plan Analysis.txt', 'Imagine Boston 2030 Analysis.txt',\n"
        "  or interview transcripts tagged with 'safety', 'violence', 'youth', 'media', 'community', 'displacement', 'government', 'structural racism'.\n"
        "  Examples: 'What does the Slow Streets program aim to achieve?',\n"
        "  'How do community members describe media representation of Dorchester?',\n"
        "  'What strategies does the Anti-Displacement Plan propose?'\n"
        "- 'hybrid': when both numbers and context are needed.\n"
        "  Examples: 'How many homicides were recorded in Dorchester last year, and what concerns about safety come up in interviews?',\n"
        "  'What are the monthly trends in 311 requests about street safety and how does Slow Streets address these?'\n\n"
        "If you choose 'rag' or 'hybrid', you may suggest up to 2 transcript_tags and policy_sources when clearly relevant.\n"
        "Respond ONLY as compact JSON with keys: mode, transcript_tags, policy_sources, k."
    )

    user_prompt = (
        "Question:\n" + question + "\n\n"
        "Policy sources include: 'Boston Anti-Displacement Plan Analysis.txt', 'Boston Slow Streets Plan Analysis.txt', 'Imagine Boston 2030 Analysis.txt'.\n"
        "Transcript tags include: safety, violence, youth, media, community, displacement, government, structural racism.\n"
        "Output JSON only."
    )

    default_plan = {
        "mode": "rag",
        "transcript_tags": None,
        "policy_sources": None,
        "k": 5,
    }

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        content = (resp.choices[0].message.content or "").strip()
        # Remove code fences if present
        if content.startswith("```"):
            content = content.strip("`").strip()
            # If the first line is a language tag, drop it
            lines = content.splitlines()
            if lines:
                if lines[0].strip().lower() in ("json", "javascript", "js"):
                    content = "\n".join(lines[1:]).strip()
        plan = _safe_json_loads(content, default_plan)
    except Exception:
        plan = default_plan

    # Normalize values
    mode = str(plan.get("mode", "rag")).lower()
    if mode not in {"sql", "rag", "hybrid"}:
        mode = "rag"
    tags = plan.get("transcript_tags")
    sources = plan.get("policy_sources")
    k = plan.get("k", 5)
    return {
        "mode": mode,
        "transcript_tags": tags if isinstance(tags, list) or tags is None else None,
        "policy_sources": sources if isinstance(sources, list) or sources is None else None,
        "k": int(k) if isinstance(k, int) else 5,
    }


def _compose_rag_answer(question: str, chunks: List[str], metadatas: List[Dict[str, Any]]) -> str:
    if not chunks:
        return "No relevant information found."

    context_parts: List[str] = []
    for idx, (chunk, meta) in enumerate(zip(chunks, metadatas), start=1):
        source = meta.get("source", "Unknown")
        doc_type = meta.get("doc_type", "unknown")
        tags = meta.get("tags", "")
        if isinstance(tags, list):
            tags_str = ", ".join(tags)
        else:
            tags_str = str(tags)
        context_parts.append(f"[Source {idx}: {source} ({doc_type}){' - Tags: ' + tags_str if tags_str else ''}]")
        context_parts.append(chunk)
        context_parts.append("")
    context = "\n".join(context_parts)

    system_prompt = (
        "You are a factual assistant answering questions about Boston community data and policies.\n"
        "Only use the provided SOURCES. Do not add information that is not supported by the text.\n"
        "Prefer quoting short phrases from the sources rather than paraphrasing too freely.\n"
        "If the question involves quantitative topics, note that RAG sources may be incomplete and avoid fabricating figures.\n"
        "Write in 2 short paragraphs. Cite sources as [Source X]."
    )
    user_prompt = (
        "SOURCES:\n" + context + "\n\n" +
        "QUESTION: " + question + "\n\n" +
        "ANSWER (2 short paragraphs):"
    )

    client = _get_llm_client()
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return "\n\n".join(context_parts[:10])  # fallback: show a sample of context


def _run_rag(question: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    k = int(plan.get("k", 5))
    tags = plan.get("transcript_tags")
    sources = plan.get("policy_sources")

    combined_chunks: List[str] = []
    combined_meta: List[Dict[str, Any]] = []

    # transcripts
    try:
        t_res = retrieval.retrieve_transcripts(question, tags=tags, k=k)
        combined_chunks.extend(t_res.get("chunks", []))
        combined_meta.extend(t_res.get("metadata", []))
    except Exception:
        pass

    # policies
    try:
        if sources:
            for src in sources:
                p_res = retrieval.retrieve_policies(question, k=k, source=src)
                combined_chunks.extend(p_res.get("chunks", []))
                combined_meta.extend(p_res.get("metadata", []))
        else:
            p_res = retrieval.retrieve_policies(question, k=k)
            combined_chunks.extend(p_res.get("chunks", []))
            combined_meta.extend(p_res.get("metadata", []))
    except Exception:
        pass

    answer = _compose_rag_answer(question, combined_chunks, combined_meta)
    return {"answer": answer, "chunks": combined_chunks, "metadata": combined_meta}


def _run_sql(question: str) -> Dict[str, Any]:
    # Import app3 only when SQL path is actually used, to avoid psycopg2 import errors otherwise
    import app3  # noqa: WPS433

    database = os.environ.get("PGSCHEMA", "public")
    schema = app3._fetch_schema_snapshot(database)
    # Base metadata from catalog selection
    metadata = app3._build_question_metadata(question)
    # If the prompt suggests mapping/locations, hint the generator to include coordinates
    want_map = any(w in (question or "").lower() for w in ["map", "maps", "where", "location", "hotspot", "cluster", "show on a map", "geo", "geography"])
    if want_map and metadata:
        try:
            meta_obj = json.loads(metadata)
        except Exception:
            meta_obj = {}
        hints = (meta_obj.get("hints") if isinstance(meta_obj, dict) else None) or {}
        hints.update({"need_location": True, "max_points": 500})
        if isinstance(meta_obj, dict):
            meta_obj["hints"] = hints
        else:
            meta_obj = {"hints": hints}
        try:
            metadata = json.dumps(meta_obj, ensure_ascii=False)
        except Exception:
            pass
    sql = app3._llm_generate_sql(question, schema, os.getenv("OPENAI_MODEL", getattr(app3, "OPENAI_MODEL", OPENAI_MODEL)), metadata)
    exec_out = app3._execute_with_retries(
        initial_sql=sql,
        question=question,
        schema=schema,
        metadata=metadata,
    )
    final_sql = exec_out.get("sql", sql)
    result = exec_out.get("result", {})
    answer = app3._llm_generate_answer(
        question,
        final_sql,
        result,
        os.getenv("OPENAI_SUMMARY_MODEL", getattr(app3, "OPENAI_SUMMARY_MODEL", OPENAI_SUMMARY_MODEL)),
    )
    return {"answer": answer, "sql": final_sql, "result": result}


def _run_hybrid(question: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    sql_part = _run_sql(question)
    rag_part = _run_rag(question, plan)

    # Merge with a short LLM call
    client = _get_llm_client()
    merge_system = (
        "You are combining two summaries:\n"
        "1. SQL-derived structured data (accurate counts, averages, statistics)\n"
        "2. RAG-derived contextual information (explanations, qualitative insights, policy details)\n\n"
        "Write a concise answer in 2 short paragraphs:\n"
        "- First paragraph: summarize key figures and patterns from the SQL data.\n"
        "- Second paragraph: explain relevant context or interpretation based on the RAG sources.\n"
        "Always cite RAG evidence as [Source X].\n"
        "Never invent data or trends not present in SQL or RAG inputs."
    )
    blob = {
        "sql_answer": sql_part.get("answer"),
        "sql_result": sql_part.get("result"),
        "rag_answer": rag_part.get("answer"),
        "rag_sources": [m.get("source", "?") for m in rag_part.get("metadata", [])][:10],
    }
    merge_user = (
        "Question:\n" + question + "\n\n" +
        "Inputs (JSON):\n" + json.dumps(blob, ensure_ascii=False, default=str)
    )
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": merge_system},
                {"role": "user", "content": merge_user},
            ],
            temperature=0,
        )
        answer = (resp.choices[0].message.content or "").strip()
    except Exception:
        answer = (sql_part.get("answer") or "") + "\n\n" + (rag_part.get("answer") or "")

    return {"answer": answer, "sql": sql_part, "rag": rag_part}


def _ensure_openai_ready() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not configured")


def main() -> None:
    _bootstrap_env()
    _fix_retrieval_vectordb_path()
    _ensure_openai_ready()

    print("\nUnified SQL + RAG Chatbot (type 'exit' to quit)\n")
    while True:
        try:
            question = input("Question> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit", ":q", "q"}:
            break

        plan = _route_question(question)
        mode = plan.get("mode", "rag")

        try:
            if mode == "sql":
                # Validate DB env only when needed
                if not os.environ.get("DATABASE_URL"):
                    print("DATABASE_URL not set; falling back to RAG.")
                    out = _run_rag(question, plan)
                    print("\nAnswer:\n" + out.get("answer", ""))
                else:
                    out = _run_sql(question)
                    print("\nAnswer:\n" + out.get("answer", ""))
            elif mode == "hybrid":
                if not os.environ.get("DATABASE_URL"):
                    print("DATABASE_URL not set; running RAG only.")
                    out = _run_rag(question, plan)
                    print("\nAnswer:\n" + out.get("answer", ""))
                else:
                    out = _run_hybrid(question, plan)
                    print("\nAnswer:\n" + out.get("answer", ""))
            else:  # rag
                out = _run_rag(question, plan)
                print("\nAnswer:\n" + out.get("answer", ""))
        except Exception as exc:  # noqa: BLE001
            print(f"Error: {exc}")


if __name__ == "__main__":
    main()


