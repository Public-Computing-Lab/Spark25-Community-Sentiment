import os
import sys
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()


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


def _check_if_needs_new_data(question: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """
    Check if the question can be answered from conversation history or needs new data retrieval.
    Returns: {"needs_new_data": bool, "reason": str}
    """
    # If no history exists, always need new data
    if not conversation_history or len(conversation_history) == 0:
        return {"needs_new_data": True, "reason": "No conversation history available"}
    
    client = _get_llm_client()
    
    # Build conversation context for analysis
    history_context = ""
    if conversation_history:
        for msg in conversation_history[-10:]:  # Last 10 messages
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role and content:
                history_context += f"{role.upper()}: {content}\n\n"
    
    system_prompt = (
        "You analyze if a user's question can be answered from conversation history or needs new data retrieval.\n\n"
        "Rules:\n"
        "- If question is a follow-up, clarification, or reference to previous answers (e.g., 'what about last year?', 'tell me more', 'break that down', 'can you elaborate') → needs_new_data = false\n"
        "- If question asks for new data, different time period not mentioned before, different metrics, or completely new topic → needs_new_data = true\n"
        "- If question references specific numbers/statistics from previous answers → needs_new_data = false\n"
        "- If question asks to compare, explain further, or provide more detail on previously discussed topics → needs_new_data = false\n\n"
        "Return ONLY valid JSON with keys: needs_new_data (boolean) and reason (brief string explaining your decision)."
    )
    
    user_prompt = (
        "Conversation History:\n" + (history_context if history_context else "(No previous conversation)") + "\n\n"
        "Current Question: " + question + "\n\n"
        "Analyze if this question can be answered from the conversation history above, or if it needs new data retrieval.\n"
        "Return JSON only."
    )
    
    default_result = {"needs_new_data": True, "reason": "Error analyzing question, defaulting to new data"}
    
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
            lines = content.splitlines()
            if lines and lines[0].strip().lower() in ("json", "javascript", "js"):
                content = "\n".join(lines[1:]).strip()
        
        result = _safe_json_loads(content, default_result)
        
        # Ensure needs_new_data is boolean
        needs_new = result.get("needs_new_data", True)
        if isinstance(needs_new, str):
            needs_new = needs_new.lower() in ("true", "yes", "1")
        result["needs_new_data"] = bool(needs_new)
        
        return result
    except Exception:
        return default_result


def _route_question(question: str) -> Dict[str, Any]:
    """
    Decide whether to answer via SQL, RAG, or HYBRID.
    Returns a dict like: {"mode": "sql|rag|hybrid", "transcript_tags": [..]|null, "policy_sources": [..]|null, "k": int}
    """
    client = _get_llm_client()

    system_prompt = (
        f"Today's date is {date.today().strftime('%A, %B %d, %Y')}.\n\n"
        "You are a routing classifier for a chatbot that combines SQL (structured data) and RAG (text documents).\n"
        "Classify the user's question into one of three modes: 'sql', 'rag', or 'hybrid'.\n\n"
        "CRITICAL ROUTING RULES - Follow these explicitly:\n\n"
        "1. CRIME-RELATED QUESTIONS → Use 'hybrid' mode (SQL tables + vector DB)\n"
        "   - ANY question about crime, arrests, offenses, homicides, shots fired, safety incidents, or criminal activity\n"
        "   - MUST use both SQL tables (for statistics/data) AND vector DB (for context/community perspectives)\n"
        "   - Examples: 'What crimes happened in Dorchester?', 'How many arrests were there?', 'Tell me about safety incidents',\n"
        "     'What do people say about crime in the community?', 'Show me crime trends and community concerns'\n"
        "   - SQL tables include: 'arrests', 'offenses', 'homicides', 'shots_fired', 'bos311_data' (for safety-related 311 requests)\n"
        "   - Vector DB contains: community meeting transcripts with 'safety' and 'violence' tags, policy documents\n\n"
        "2. EVENT/CALENDAR/FUN QUESTIONS → Use 'sql' mode (weekly_events table)\n"
        "   - Questions about events, activities, schedules, calendars, 'what's happening', 'what's going on', fun activities\n"
        "   - Examples: 'What events are happening this week?', 'Show me fun activities for kids',\n"
        "     'What public meetings are scheduled?', 'Tell me about upcoming events', 'What's happening on Saturday?',\n"
        "     'Are there any community events?', 'What activities are available?'\n"
        "   - Use the 'weekly_events' SQL table which contains event details, dates, times, categories, descriptions\n"
        "   - Set 'k' to at least 5 for event queries to ensure multiple events are retrieved\n"
        "   - NOTE: Calendar events are stored in SQL (weekly_events table), NOT in the vector database\n\n"
        "3. OPINION/PERSPECTIVE QUESTIONS → Use 'rag' mode (vector DB only)\n"
        "   - Questions asking for opinions, perspectives, feelings, community views, what people think/say/believe\n"
        "   - Examples: 'What do people think about...?', 'How do community members feel about...?',\n"
        "     'What are people's opinions on...?', 'What do residents say about...?', 'How do people describe...?',\n"
        "     'What concerns do community members have?', 'What are people's views on displacement?'\n"
        "   - Use vector DB with transcript tags like 'community', 'displacement', 'safety', 'youth', 'media', etc.\n"
        "   - These are qualitative questions that require searching community meeting transcripts and documents\n\n"
        "GENERAL ROUTING GUIDELINES:\n\n"
        "- 'sql': for pure statistics, counts, trends, comparisons, numeric breakdowns from Postgres/MySQL tables\n"
        "  (service_requests/311, arrests, offenses, homicides, shots_fired, weekly_events, or other Dorchester-focused tables).\n"
        "  NOTE: This system is configured for DORCHESTER ONLY. All SQL queries automatically filter to Dorchester data only.\n"
        "  Examples: 'How many 311 service requests were filed in Dorchester last month?',\n"
        "  'What is the trend in shots fired by year in Dorchester?',\n"
        "  'Which areas in Dorchester have the highest arrests in 2023?',\n"
        "  'What events are happening this week?' (use SQL for events)\n\n"
        "- 'rag': ONLY for purely qualitative, descriptive, or policy questions answered by documents/transcripts\n"
        "  (policy documents, interview transcripts, newsletters, client-uploaded files, OR opinion/perspective questions).\n"
        "  Examples: 'What does the Slow Streets program aim to achieve?',\n"
        "  'What strategies does the Anti-Displacement Plan propose?',\n"
        "  'What was in the latest newsletter?',\n"
        "  'What do people think about media representation?' (opinion question → RAG)\n\n"
        "- 'hybrid': Use when BOTH numbers/data AND context are needed, OR for crime-related questions (see rule #1 above).\n"
        "  Examples: 'How many homicides were recorded in Dorchester last year, and what concerns about safety come up in interviews?',\n"
        "  'What are the monthly trends in 311 requests about street safety in Dorchester and how does Slow Streets address these?',\n"
        "  'Show me where crime incidents occurred in Dorchester' (crime question → hybrid)\n"
        "  NOTE: This system is configured for DORCHESTER ONLY. All SQL queries automatically filter to Dorchester data only.\n\n"
        "Available document types in the vector database:\n"
        "- 'transcript': community meeting transcripts with tags like 'safety', 'violence', 'youth', 'media', 'community', 'displacement', 'government', 'structural racism'\n"
        "- 'policy': city policy documents like 'Boston Anti-Displacement Plan Analysis.txt', 'Boston Slow Streets Plan Analysis.txt', 'Imagine Boston 2030 Analysis.txt'\n"
        "- 'client_upload': documents uploaded from Google Drive, organized in folders: 'newsletters', 'policy', 'transcripts'\n\n"
        "If you choose 'rag' or 'hybrid', you may suggest:\n"
        "- up to 2 transcript_tags when relevant. NOTE: For podcast-related queries, usually use the 'media' tag.\n"
        "  For crime-related hybrid queries, use tags like 'safety' or 'violence'.\n"
        "  For opinion questions, use tags like 'community', 'displacement', 'youth', etc.\n"
        "- policy_sources when asking about specific policy documents\n"
        "- folder_categories when asking about client-uploaded documents (newsletters, policy, transcripts)\n"
        "- 'k': number of document chunks to retrieve (must be between 3 and 10, default 5). For event/calendar questions, use at least 5.\n"
        "Respond ONLY as compact JSON with keys: mode, transcript_tags, policy_sources, folder_categories, k."
    )

    user_prompt = (
        "Question:\n" + question + "\n\n"
        "Policy sources include: 'Boston Anti-Displacement Plan Analysis.txt', 'Boston Slow Streets Plan Analysis.txt', 'Imagine Boston 2030 Analysis.txt'.\n"
        "Transcript tags include: safety, violence, youth, media, community, displacement, government, structural racism.\n"
        "Folder categories (for client uploads): newsletters, policy, transcripts.\n"
        "Output JSON only."
    )

    default_plan = {
        "mode": "hybrid",
        "transcript_tags": None,
        "policy_sources": None,
        "folder_categories": None,
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
    folders = plan.get("folder_categories")
    k = plan.get("k", 5)
    
    # Normalize and validate k
    try:
        k = int(k)
    except (ValueError, TypeError):
        k = 5
    
    # Ensure k is at least 3 (minimum for useful retrieval)
    if k < 3:
        k = 3
    
    # Force higher k for calendar questions to ensure good event coverage
    if _is_calendar_question(question):
        # Ensure at least 5 results for calendar queries
        if k < 5:
            k = 5
    
    # Cap k at reasonable maximum (20)
    if k > 20:
        k = 20

    return {
        "mode": mode,
        "transcript_tags": tags if isinstance(tags, list) or tags is None else None,
        "policy_sources": sources if isinstance(sources, list) or sources is None else None,
        "folder_categories": folders if isinstance(folders, list) or folders is None else None,
        "k": k,
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
        "You are a friendly, non-technical assistant helping people understand Dorchester community data and policies.\n"
        "This system is configured for DORCHESTER ONLY. All data queries are automatically filtered to Dorchester only.\n"
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


def _answer_from_history(question: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
    """
    Generate an answer from conversation history only, without retrieving new data.
    This is used for follow-up questions that can be answered from previous context.
    """
    if not conversation_history:
        return "I don't have any previous conversation to reference. Could you ask your question again?"
    
    client = _get_llm_client()
    model = client.GenerativeModel(GEMINI_MODEL)
    
    system_prompt = (
        "You are a friendly, non-technical assistant helping people understand Dorchester community data and policies.\n"
        "This system is configured for DORCHESTER ONLY. All data queries are automatically filtered to Dorchester only.\n"
        "Use clear, everyday language and imagine you are talking to a neighbor, not a technical expert.\n\n"
        "Answer the user's question based ONLY on the conversation history provided. "
        "Do not mention that you're using conversation history - just answer naturally as if continuing the conversation.\n"
        "If the question references previous answers, numbers, or statistics mentioned earlier, use those in your response.\n"
        "If you cannot answer from the conversation history, politely say so and suggest they ask a new question.\n"
        "Avoid technical jargon, and do not mention SQL, databases, RAG, retrieval methods, or internal tools."
    )
    
    # Build conversation context
    history_text = ""
    for msg in conversation_history[-20:]:  # Last 20 messages for context
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role and content:
            history_text += f"{role.upper()}: {content}\n\n"
    
    user_prompt = (
        "Conversation History:\n" + history_text + "\n\n"
        "Current Question: " + question + "\n\n"
        "Please answer the current question based on the conversation history above:"
    )
    
    try:
        resp = model.generate_content(
            user_prompt,
            generation_config={"temperature": 0.3}
        )
        return (resp.text or "").strip()
    except Exception:
        return "I encountered an error answering from conversation history. Could you rephrase your question?"


def _is_calendar_question(question: str) -> bool:
    """Check if the question is about events, calendar, or schedules."""
    calendar_keywords = [
        "event", "events", "happening", "schedule", "calendar", "activity", "activities",
        "this week", "next week", "today", "tomorrow", "weekend", "saturday", "sunday",
        "monday", "tuesday", "wednesday", "thursday", "friday", "what's on", "what is on",
        "going on", "things to do", "community event", "meeting", "workshop"
    ]
    question_lower = question.lower()
    return any(kw in question_lower for kw in calendar_keywords)


def _run_rag(question: str, plan: Dict[str, Any], conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    k = int(plan.get("k", 5))
    tags = plan.get("transcript_tags")
    sources = plan.get("policy_sources")

    combined_chunks: List[str] = []
    combined_meta: List[Dict[str, Any]] = []

    # NOTE: Calendar events are now SQL-only (weekly_events table), not in vector DB.
    # Event queries should use 'sql' or 'hybrid' mode which handles them via SQL.

    # transcripts
    try:
        t_res = retrieval.retrieve_transcripts(question, tags=tags, k=k)
        t_chunks = t_res.get("chunks", [])
        print(f"  📝 Transcripts: {len(t_chunks)} chunks found")
        combined_chunks.extend(t_chunks)
        combined_meta.extend(t_res.get("metadata", []))
    except Exception as e:
        print(f"  ⚠️ Transcript retrieval error: {e}")

    # policies
    try:
        if sources:
            for src in sources:
                p_res = retrieval.retrieve_policies(question, k=k, source=src)
                combined_chunks.extend(p_res.get("chunks", []))
                combined_meta.extend(p_res.get("metadata", []))
        else:
            p_res = retrieval.retrieve_policies(question, k=k)
            p_chunks = p_res.get("chunks", [])
            print(f"  📋 Policies: {len(p_chunks)} chunks found")
            combined_chunks.extend(p_chunks)
            combined_meta.extend(p_res.get("metadata", []))
    except Exception as e:
        print(f"  ⚠️ Policy retrieval error: {e}")

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
        "You are a friendly, non-technical assistant explaining information about DORCHESTER ONLY to a general audience.\n"
        "This system is configured for DORCHESTER ONLY. All data queries are automatically filtered to Dorchester only.\n"
        "Use clear, everyday language and speak as if you are talking directly to the user.\n"
        "You have access to both numeric data (counts, trends, patterns) and contextual information (people's experiences, policy documents, community perspectives).\n\n"
        "Weave these together naturally into a single, cohesive answer that tells a complete story.\n"
        "Blend the numbers with the context so the user understands both what is happening and why it matters.\n"
        "Focus on what the information means for people in Dorchester, not on technical details or data sources.\n"
        "If you see any data from other neighborhoods, ignore it completely and only discuss Dorchester.\n\n"
        "Do NOT mention SQL, databases, RAG, retrieval, or any internal tools. Just speak as a helpful information bot.\n"
        "Never invent data or trends not present in the inputs."
        + ("\n\nYou are in a conversation. Reference previous questions naturally when it helps the user." if conversation_history else "")
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
        
        # Print the routing plan
        print(f"\n🧭 Routing Plan: {json.dumps(plan, indent=2)}\n")

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


