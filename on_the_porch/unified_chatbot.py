import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Ensure we can import RAG utilities from the directory with a space in its name
_THIS_FILE = Path(__file__).resolve()
_REAL_DIR = _THIS_FILE.parent
_ROOT_DIR = _REAL_DIR.parent.parent
# RAG utilities live in `on_the_porch/rag stuff`
_RAG_DIR = _REAL_DIR / "rag stuff"
if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))


# Import RAG retrieval helpers; import SQL pipeline lazily only when needed
import retrieval  # type: ignore  # noqa: E402

# Local Gemini client config (avoid importing app3 at module load)
try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # type: ignore

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_SUMMARY_MODEL = os.getenv("GEMINI_SUMMARY_MODEL", GEMINI_MODEL)


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
        expected = _REAL_DIR / "vectordb_new"
        retrieval.VECTORDB_DIR = expected  # type: ignore[attr-defined]
    except Exception:
        pass


def _get_llm_client():
    if genai is None:
        raise RuntimeError("gemini client not installed: pip install google-generativeai")
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
    return genai


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
    client = _get_llm_client()

    system_prompt = (
        "You are a routing classifier for a chatbot that combines SQL (structured data) and RAG (text documents).\n"
        "Classify the user's question into one of three modes: 'sql', 'rag', or 'hybrid'.\n\n"
        "Use the following logic with examples grounded in our data:\n"
        "- 'sql': for pure statistics, counts, trends, comparisons, numeric breakdowns from Postgres/MySQL tables like\n"
        "  'service_requests' (311), 'arrests', 'offenses', 'homicides', 'shots_fired', or Dorchester-focused tables.\n"
        "  Examples: 'How many 311 service requests were filed in Dorchester last month?',\n"
        "  'What is the trend in shots fired by year in Boston?',\n"
        "  'Which neighborhoods have the highest arrests in 2023?'\n"
        "- 'rag': ONLY for purely qualitative, descriptive, or policy questions answered by documents/transcripts, such as\n"
        "  'Boston Anti-Displacement Plan Analysis.txt', 'Boston Slow Streets Plan Analysis.txt', 'Imagine Boston 2030 Analysis.txt',\n"
        "  or interview transcripts tagged with 'safety', 'violence', 'youth', 'media', 'community', 'displacement', 'government', 'structural racism'.\n"
        "  Examples: 'What does the Slow Streets program aim to achieve?',\n"
        "  'How do community members describe media representation of Dorchester?',\n"
        "  'What strategies does the Anti-Displacement Plan propose?'\n"
        "- 'hybrid': PREFERRED when both numbers and context are needed, OR when questions involve location/data visualization, "
        "  OR when questions are about events, calendars, schedules, or \"what is happening\" on a given day or week so you can use both weekly events SQL data and RAG documents.\n"
        "  Examples: 'How many homicides were recorded in Dorchester last year, and what concerns about safety come up in interviews?',\n"
        "  'What are the monthly trends in 311 requests about street safety and how does Slow Streets address these?',\n"
        "  'Show me where crime incidents occurred in Dorchester',\n"
        "  'What locations have the most service requests?',\n"
        "  'What events are happening this week?',\n"
        "  'What activities are available for kids on Saturday?'\n\n"
        "IMPORTANT: When questions involve 'where', 'location', 'map', 'show', 'visualize', 'geography', spatial data, "
        "or events/calendars/schedules, prefer 'hybrid' mode to combine SQL (including weekly events tables) with RAG context.\n"
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
        "mode": "hybrid",
        "transcript_tags": None,
        "policy_sources": None,
        "k": 5,
    }

    try:
        model = client.GenerativeModel(GEMINI_MODEL)
        prompt = f"{system_prompt}\n\n{user_prompt}"
        resp = model.generate_content(
            prompt,
            generation_config={"temperature": 0}
        )
        content = (resp.text or "").strip()
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
    mode = str(plan.get("mode", "hybrid")).lower()
    if mode not in {"sql", "rag", "hybrid"}:
        mode = "hybrid"  # Default to hybrid for safety
    tags = plan.get("transcript_tags")
    sources = plan.get("policy_sources")
    k = plan.get("k", 5)

    return {
        "mode": mode,
        "transcript_tags": tags if isinstance(tags, list) or tags is None else None,
        "policy_sources": sources if isinstance(sources, list) or sources is None else None,
        "k": int(k) if isinstance(k, int) else 5,
    }


def _compose_rag_answer(question: str, chunks: List[str], metadatas: List[Dict[str, Any]], conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
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
        "You are a friendly, non-technical assistant helping people understand Boston community data and policies.\n"
        "Use clear, everyday language and imagine you are talking to a neighbor, not a technical expert.\n"
        "Use only the provided SOURCES and do not add information that is not supported by the text.\n\n"
        "When you quote or paraphrase people or documents, briefly explain who or what they are first, "
        "then include the quote in a natural way. Avoid technical jargon, and do not mention SQL, databases, RAG, "
        "retrieval methods, or internal tools.\n"
        "If the question involves numbers, be honest when the sources are limited and avoid inventing precise figures.\n"
        + ("\n\nYou are in a conversation. Use previous messages for context when the current question references earlier topics or asks for follow-ups." if conversation_history else "")
    )
    user_prompt = (
        "SOURCES:\n" + context + "\n\n" +
        "QUESTION: " + question + "\n\n" +
        "Please answer for the user in clear, everyday language:"
    )

    client = _get_llm_client()
    model = client.GenerativeModel(GEMINI_MODEL)
    
    # Build conversation context
    full_prompt = system_prompt + "\n\n"
    if conversation_history:
        for msg in conversation_history[-10:]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            full_prompt += f"{role.upper()}: {content}\n\n"
    full_prompt += user_prompt
    
    try:
        resp = model.generate_content(
            full_prompt,
            generation_config={"temperature": 0.3}
        )
        return (resp.text or "").strip()
    except Exception:
        return "\n\n".join(context_parts[:10])  # fallback: show a sample of context


def _run_rag(question: str, plan: Dict[str, Any], conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
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

    answer = _compose_rag_answer(question, combined_chunks, combined_meta, conversation_history)
    return {"answer": answer, "chunks": combined_chunks, "metadata": combined_meta}


def _run_sql(question: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    # Import app4 (MySQL) only when SQL path is actually used
    import sql_chat.app4 as app4  # noqa: WPS433

    database = os.environ.get("PGSCHEMA", "public")
    schema = app4._fetch_schema_snapshot(database)
    # Base metadata from catalog selection
    metadata = app4._build_question_metadata(question)
    # Strongly encourage maps for location-related queries and many data queries
    location_keywords = ["map", "maps", "where", "location", "locations", "hotspot", "cluster", "show on a map", "geo", "geography", "near", "place", "places", "area", "neighborhood", "neighborhoods"]
    data_visualization_keywords = ["show", "display", "visualize", "see", "find", "list"]
    question_lower = (question or "").lower()
    want_map = any(w in question_lower for w in location_keywords) or any(w in question_lower for w in data_visualization_keywords)
    
    # Default to including location when possible
    if metadata:
        try:
            meta_obj = json.loads(metadata)
        except Exception:
            meta_obj = {}
        hints = (meta_obj.get("hints") if isinstance(meta_obj, dict) else None) or {}
        if want_map:
            hints.update({"need_location": True, "max_points": 500})
        else:
            # Even if not explicitly asked, suggest including location when tables have coordinates
            hints.update({"prefer_location": True, "max_points": 500})
        if isinstance(meta_obj, dict):
            meta_obj["hints"] = hints
        else:
            meta_obj = {"hints": hints}
        try:
            metadata = json.dumps(meta_obj, ensure_ascii=False)
        except Exception:
            pass
    else:
        # Even without metadata, create hints to encourage maps
        try:
            meta_obj = {"hints": {"prefer_location": True, "max_points": 500}}
            metadata = json.dumps(meta_obj, ensure_ascii=False)
        except Exception:
            pass
    sql = app4._llm_generate_sql(question, schema, os.getenv("GEMINI_MODEL", getattr(app4, "GEMINI_MODEL", GEMINI_MODEL)), metadata, conversation_history)
    exec_out = app4._execute_with_retries(
        initial_sql=sql,
        question=question,
        schema=schema,
        metadata=metadata,
    )
    final_sql = exec_out.get("sql", sql)
    result = exec_out.get("result", {})
    answer = app4._llm_generate_answer(
        question,
        final_sql,
        result,
        os.getenv("GEMINI_SUMMARY_MODEL", getattr(app4, "GEMINI_SUMMARY_MODEL", GEMINI_SUMMARY_MODEL)),
        conversation_history,
    )
    return {"answer": answer, "sql": final_sql, "result": result}


def _run_hybrid(question: str, plan: Dict[str, Any], conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    sql_part = _run_sql(question, conversation_history)
    rag_part = _run_rag(question, plan, conversation_history)

    # Merge with a short LLM call
    client = _get_llm_client()
    model = client.GenerativeModel(GEMINI_MODEL)
    merge_system = (
        "You are a friendly assistant answering questions for a non-technical user.\n"
        "You receive two kinds of input: (1) numeric data about counts and trends, and (2) contextual text explaining people's experiences and policies.\n"
        "Blend these into a single, clear answer in everyday language.\n\n"
        "Write a concise answer in 2 short paragraphs:\n"
        "- First paragraph: summarize the most important numbers and patterns (who/what/when/where).\n"
        "- Second paragraph: explain what those numbers might mean in people's lives, using the contextual text.\n"
        "Do NOT mention SQL, databases, RAG, retrieval, or any internal tools. Just speak as a normal information bot.\n"
        "Never invent data or trends not present in the inputs."
        + ("\n\nYou are in a conversation. Use previous messages for context when the current question references earlier topics." if conversation_history else "")
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
    
    # Build full prompt with conversation history
    full_prompt = merge_system + "\n\n"
    if conversation_history:
        for msg in conversation_history[-10:]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            full_prompt += f"{role.upper()}: {content}\n\n"
    full_prompt += merge_user
    
    try:
        resp = model.generate_content(
            full_prompt,
            generation_config={"temperature": 0}
        )
        answer = (resp.text or "").strip()
    except Exception:
        answer = (sql_part.get("answer") or "") + "\n\n" + (rag_part.get("answer") or "")

    return {"answer": answer, "sql": sql_part, "rag": rag_part}


def _ensure_gemini_ready() -> None:
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY not configured")


def main() -> None:
    _bootstrap_env()
    _fix_retrieval_vectordb_path()
    _ensure_gemini_ready()

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


