import os
import sys
import json
from datetime import date, datetime
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


# ---------------------------------------------------------------------------
# Retrieval Cache: stores the most recent retrieval results for follow-up use
# ---------------------------------------------------------------------------

def create_empty_cache() -> Dict[str, Any]:
    """Create an empty retrieval cache structure."""
    return {
        "mode": None,  # "sql", "rag", or "hybrid"
        "timestamp": None,
        "question": None,
        "sql_result": None,  # Raw SQL rows/data
        "sql_query": None,
        "rag_chunks": None,  # List of text chunks
        "rag_metadata": None,  # List of metadata dicts
        "answer": None,  # The generated answer
    }


def build_retrieval_cache(
    mode: str,
    question: str,
    answer: str,
    sql_result: Optional[Dict[str, Any]] = None,
    sql_query: Optional[str] = None,
    rag_chunks: Optional[List[str]] = None,
    rag_metadata: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a retrieval cache from the results of a query."""
    return {
        "mode": mode,
        "timestamp": datetime.now().isoformat(),
        "question": question,
        "sql_result": sql_result,
        "sql_query": sql_query,
        "rag_chunks": rag_chunks[:20] if rag_chunks else None,  # Cap chunks
        "rag_metadata": rag_metadata[:20] if rag_metadata else None,
        "answer": answer,
    }


def summarize_cache(cache: Optional[Dict[str, Any]]) -> str:
    """Create a concise text summary of what's in the cache for the LLM."""
    if not cache or not cache.get("mode"):
        return "(No cached data available)"
    
    parts = []
    mode = cache.get("mode", "unknown")
    question = cache.get("question", "")
    timestamp = cache.get("timestamp", "")
    
    parts.append(f"Cached data from mode '{mode}' for question: \"{question}\"")
    if timestamp:
        parts.append(f"Retrieved at: {timestamp}")
    
    # Summarize SQL results
    sql_result = cache.get("sql_result")
    if sql_result:
        rows = sql_result.get("rows", [])
        columns = sql_result.get("columns", [])
        row_count = len(rows) if isinstance(rows, list) else 0
        col_names = ", ".join(columns[:10]) if columns else "unknown columns"
        parts.append(f"SQL data: {row_count} rows with columns [{col_names}]")
        
        # Include actual data preview (first few rows)
        if rows and row_count > 0:
            preview_rows = rows[:10]  # First 10 rows for preview
            parts.append(f"Data preview (first {len(preview_rows)} rows):")
            for i, row in enumerate(preview_rows, 1):
                if isinstance(row, dict):
                    row_str = ", ".join(f"{k}: {v}" for k, v in list(row.items())[:6])
                elif isinstance(row, (list, tuple)):
                    row_str = ", ".join(str(v) for v in row[:6])
                else:
                    row_str = str(row)[:200]
                parts.append(f"  Row {i}: {row_str}")
    
    # Summarize RAG chunks
    rag_meta = cache.get("rag_metadata")
    rag_chunks = cache.get("rag_chunks")
    if rag_meta:
        chunk_count = len(rag_meta)
        sources = list(set(m.get("source", "unknown") for m in rag_meta[:10]))
        doc_types = list(set(m.get("doc_type", "unknown") for m in rag_meta[:10]))
        parts.append(f"RAG data: {chunk_count} chunks from sources: {sources[:5]}, types: {doc_types}")
        
        # Include chunk previews
        if rag_chunks:
            parts.append(f"Chunk previews (first {min(5, len(rag_chunks))}):")
            for i, chunk in enumerate(rag_chunks[:5], 1):
                preview = chunk[:300] + "..." if len(chunk) > 300 else chunk
                parts.append(f"  Chunk {i}: {preview}")
    
    return "\n".join(parts)


def _check_if_needs_new_data(
    question: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    retrieval_cache: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Check if the question can be answered from conversation history and/or cached data.
    Returns: {"needs_new_data": bool, "reason": str}
    """
    # If no history and no cache, always need new data
    has_history = conversation_history and len(conversation_history) > 0
    has_cache = retrieval_cache and retrieval_cache.get("mode")
    
    if not has_history and not has_cache:
        return {"needs_new_data": True, "reason": "No conversation history or cached data available"}
    
    client = _get_llm_client()
    
    # Build conversation context for analysis
    history_context = ""
    if conversation_history:
        for msg in conversation_history[-10:]:  # Last 10 messages
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role and content:
                history_context += f"{role.upper()}: {content}\n\n"
    
    # Build cache summary
    cache_summary = summarize_cache(retrieval_cache)
    
    system_prompt = (
        "You analyze if a user's question can be answered from conversation history and/or cached retrieval data, or if it needs new data retrieval.\n\n"
        "You have access to:\n"
        "1. Conversation history (previous Q&A exchanges)\n"
        "2. Cached data (the actual data rows/chunks from the most recent retrieval)\n\n"
        "Rules:\n"
        "- If the cached data contains the information needed to answer the question → needs_new_data = false\n"
        "- If question is a follow-up asking for more detail about items in the cached data (e.g., 'tell me more about event #2', 'what about the first one') → needs_new_data = false\n"
        "- If question is a follow-up, clarification, or reference to previous answers → needs_new_data = false\n"
        "- If question asks for new data, different time period not in cache, different metrics, or completely new topic → needs_new_data = true\n"
        "- If question references specific items visible in the cached data preview → needs_new_data = false\n"
        "- If question asks to compare, explain, or provide more detail on cached data → needs_new_data = false\n\n"
        "Return ONLY valid JSON with keys: needs_new_data (boolean) and reason (brief string explaining your decision)."
    )
    
    user_prompt = (
        "Conversation History:\n" + (history_context if history_context else "(No previous conversation)") + "\n\n"
        "Cached Data:\n" + cache_summary + "\n\n"
        "Current Question: " + question + "\n\n"
        "Analyze if this question can be answered from the conversation history and/or cached data above, or if it needs new data retrieval.\n"
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
        "You are a STRICT routing classifier for a chatbot that combines SQL (structured data) and RAG (text documents).\n"
        "You MUST classify the user's question into EXACTLY one of three modes: 'sql', 'rag', or 'hybrid'.\n"
        "These rules are MANDATORY and NON-NEGOTIABLE. Follow them EXACTLY.\n\n"
        "═══════════════════════════════════════════════════════════════════════════════\n"
        "CRITICAL ROUTING RULES - ABSOLUTE PRIORITY (CHECK IN THIS ORDER):\n"
        "═══════════════════════════════════════════════════════════════════════════════\n\n"
        "RULE 1: CRIME-RELATED QUESTIONS → Route based on question type\n"
        "   - If the question mentions ANY of: crime, crimes, arrest, arrests, offense, offenses, homicide, homicides, shooting, shootings, shots fired, safety incident, safety incidents, criminal activity, violence, violent\n"
        "   - THEN apply these sub-rules:\n"
        "     a) If asking for STATISTICS/NUMBERS ONLY (counts, trends, comparisons, breakdowns) → mode MUST be 'sql'\n"
        "        Examples: 'How many arrests were there?', 'What is the trend in shots fired?', 'Show me crime statistics', 'Which areas have highest arrests?' → sql\n"
        "     b) If asking for OPINIONS/CONTEXT ONLY (what people think/say about crime) → mode MUST be 'hybrid'\n"
        "        Examples: 'What do people say about crime?', 'How do residents feel about safety?' → hybrid\n"
        "     c) If asking for BOTH statistics AND context/opinions → mode MUST be 'hybrid'\n"
        "        Examples: 'How many homicides and what concerns come up?', 'Show crime trends and community concerns' → hybrid\n"
        "   - DO NOT use 'rag' alone for crime questions\n\n"
        "RULE 2: EVENT/CALENDAR/ACTIVITY QUESTIONS → ALWAYS 'sql' mode\n"
        "   - If the question mentions ANY of: event, events, happening, schedule, calendar, activity, activities, 'what's on', 'what is on', 'going on', meeting, meetings, workshop, workshops, 'this week', 'next week', 'today', 'tomorrow', 'weekend', day of week\n"
        "   - THEN mode MUST be 'sql' (NO EXCEPTIONS)\n"
        "   - DO NOT use 'rag' or 'hybrid' for event/calendar questions\n"
        "   - Examples that MUST be 'sql':\n"
        "     * 'What events are happening this week?' → sql\n"
        "     * 'Show me fun activities for kids' → sql\n"
        "     * 'What public meetings are scheduled?' → sql\n"
        "     * 'What's happening on Saturday?' → sql\n"
        "     * 'Are there any community events?' → sql\n\n"
        "RULE 3: OPINION/PERSPECTIVE QUESTIONS → ALWAYS 'rag' mode\n"
        "   - If the question asks for: opinions, perspectives, feelings, views, what people think/say/believe/feel/describe, community views, resident views\n"
        "   - AND the question is NOT about crime (see Rule 1)\n"
        "   - THEN mode MUST be 'rag' (NO EXCEPTIONS)\n"
        "   - DO NOT use 'sql' or 'hybrid' for pure opinion questions\n"
        "   - Examples that MUST be 'rag':\n"
        "     * 'What do people think about displacement?' → rag\n"
        "     * 'How do community members feel about housing?' → rag\n"
        "     * 'What are people's opinions on media representation?' → rag\n"
        "     * 'What do residents say about the neighborhood?' → rag\n\n"
        "═══════════════════════════════════════════════════════════════════════════════\n"
        "SECONDARY ROUTING RULES (Apply if Rules 1-3 don't match):\n"
        "═══════════════════════════════════════════════════════════════════════════════\n\n"
        "RULE 4: PURE STATISTICS/NUMBERS → 'sql' mode\n"
        "   - Questions asking ONLY for: counts, numbers, statistics, trends, comparisons, breakdowns, aggregations\n"
        "   - Questions that can be answered with numeric data from tables\n"
        "   - This INCLUDES crime statistics (see Rule 1a)\n"
        "   - Examples: 'How many 311 requests?', 'What is the trend in shots fired?', 'Which areas have highest arrests?', 'How many homicides last year?'\n"
        "   - DO NOT use 'rag' or 'hybrid' if the question is purely numeric\n\n"
        "RULE 5: POLICY/DOCUMENT CONTENT → 'rag' mode\n"
        "   - Questions asking about: what a policy/document says, what a program aims to achieve, document content, newsletter content\n"
        "   - Examples: 'What does Slow Streets aim to achieve?', 'What strategies does the Anti-Displacement Plan propose?', 'What was in the newsletter?'\n"
        "   - DO NOT use 'sql' for document content questions\n\n"
        "RULE 6: COMBINED DATA + CONTEXT → 'hybrid' mode\n"
        "   - Questions that explicitly ask for BOTH numbers/data AND context/explanation\n"
        "   - Examples: 'How many homicides and what concerns come up?', 'Show trends and how policies address them'\n"
        "   - DO NOT use 'sql' or 'rag' alone if question explicitly requires both\n\n"
        "═══════════════════════════════════════════════════════════════════════════════\n"
        "STRICT VALIDATION REQUIREMENTS:\n"
        "═══════════════════════════════════════════════════════════════════════════════\n\n"
        "1. Mode MUST be exactly one of: 'sql', 'rag', or 'hybrid' (lowercase, no quotes in JSON)\n"
        "2. If mode is 'sql': transcript_tags, policy_sources, and folder_categories MUST be null\n"
        "3. If mode is 'rag' or 'hybrid':\n"
        "   - transcript_tags: array of 0-2 strings OR null (valid tags: safety, violence, youth, media, community, displacement, government, structural racism)\n"
        "   - policy_sources: array of strings OR null (valid: 'Boston Anti-Displacement Plan Analysis.txt', 'Boston Slow Streets Plan Analysis.txt', 'Imagine Boston 2030 Analysis.txt')\n"
        "   - folder_categories: array of strings OR null (valid: newsletters, policy, transcripts)\n"
        "   - k: integer between 3 and 10 (default 5, minimum 5 for event queries)\n"
        "4. For crime questions using 'hybrid' mode (Rule 1b or 1c): transcript_tags MUST include at least one of: 'safety' or 'violence'\n"
        "   For crime questions using 'sql' mode (Rule 1a): transcript_tags, policy_sources, and folder_categories MUST be null\n"
        "5. For opinion questions (Rule 3): transcript_tags should include relevant tags like 'community', 'displacement', 'youth', 'media'\n"
        "6. For event questions (Rule 2): k MUST be at least 5\n\n"
        "═══════════════════════════════════════════════════════════════════════════════\n"
        "OUTPUT FORMAT (STRICT):\n"
        "═══════════════════════════════════════════════════════════════════════════════\n\n"
        "Return ONLY valid JSON with EXACTLY these keys: mode, transcript_tags, policy_sources, folder_categories, k\n"
        "DO NOT include any explanatory text, markdown, code blocks, or additional content.\n"
        "DO NOT use backticks or markdown formatting.\n"
        "Example valid output:\n"
        '{"mode": "hybrid", "transcript_tags": ["safety"], "policy_sources": null, "folder_categories": null, "k": 5}\n\n'
        "NOTE: This system is configured for DORCHESTER ONLY. All SQL queries automatically filter to Dorchester data only."
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


def _answer_from_history(
    question: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    retrieval_cache: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate an answer from conversation history and/or cached retrieval data.
    This is used for follow-up questions that can be answered from previous context.
    """
    has_history = conversation_history and len(conversation_history) > 0
    has_cache = retrieval_cache and retrieval_cache.get("mode")
    
    if not has_history and not has_cache:
        return "I don't have any previous conversation or data to reference. Could you ask your question again?"
    
    client = _get_llm_client()
    model = client.GenerativeModel(GEMINI_MODEL)
    
    # Build the context from cache
    cache_context = ""
    if has_cache:
        cache_context = _build_cache_context_for_answer(retrieval_cache)
    
    system_prompt = (
        "You are a friendly, non-technical assistant helping people understand Dorchester community data and policies.\n"
        "This system is configured for DORCHESTER ONLY. All data queries are automatically filtered to Dorchester only.\n"
        "Use clear, everyday language and imagine you are talking to a neighbor, not a technical expert.\n\n"
        "Answer the user's question based on the conversation history and cached data provided. "
        "Do not mention that you're using cached data or conversation history - just answer naturally as if continuing the conversation.\n"
        "If the question asks about specific items (e.g., 'tell me more about event #2', 'what about the first one'), "
        "use the cached data to provide detailed information about those specific items.\n"
        "If the question references previous answers, numbers, or statistics, use those in your response.\n"
        "If you cannot answer from the available information, politely say so and suggest they ask a new question.\n"
        "Avoid technical jargon, and do not mention SQL, databases, RAG, retrieval methods, or internal tools."
    )
    
    # Build conversation context
    history_text = ""
    if conversation_history:
        for msg in conversation_history[-20:]:  # Last 20 messages for context
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role and content:
                history_text += f"{role.upper()}: {content}\n\n"
    
    user_prompt = ""
    if history_text:
        user_prompt += "Conversation History:\n" + history_text + "\n\n"
    if cache_context:
        user_prompt += "Available Data (from recent retrieval):\n" + cache_context + "\n\n"
    user_prompt += "Current Question: " + question + "\n\n"
    user_prompt += "Please answer the current question using the available information:"
    
    try:
        full_prompt = system_prompt + "\n\n" + user_prompt
        resp = model.generate_content(
            full_prompt,
            generation_config={"temperature": 0.3}
        )
        return (resp.text or "").strip()
    except Exception:
        return "I encountered an error answering from the available information. Could you rephrase your question?"


def _build_cache_context_for_answer(cache: Dict[str, Any]) -> str:
    """Build a detailed context string from cache for answering questions."""
    parts = []
    
    # Include SQL results
    sql_result = cache.get("sql_result")
    if sql_result:
        rows = sql_result.get("rows", [])
        columns = sql_result.get("columns", [])
        
        if rows and columns:
            parts.append(f"Data table with {len(rows)} entries:")
            parts.append(f"Columns: {', '.join(columns)}")
            parts.append("")
            
            # Include all rows (up to a reasonable limit) with numbering
            for i, row in enumerate(rows[:50], 1):
                if isinstance(row, dict):
                    row_items = [f"{k}: {v}" for k, v in row.items()]
                    parts.append(f"Entry {i}: {', '.join(row_items)}")
                elif isinstance(row, (list, tuple)) and columns:
                    row_items = [f"{columns[j]}: {row[j]}" for j in range(min(len(columns), len(row)))]
                    parts.append(f"Entry {i}: {', '.join(row_items)}")
                else:
                    parts.append(f"Entry {i}: {row}")
            
            if len(rows) > 50:
                parts.append(f"... and {len(rows) - 50} more entries")
    
    # Include RAG chunks
    rag_chunks = cache.get("rag_chunks", [])
    rag_meta = cache.get("rag_metadata", [])
    
    if rag_chunks:
        parts.append("")
        parts.append(f"Document excerpts ({len(rag_chunks)} chunks):")
        for i, (chunk, meta) in enumerate(zip(rag_chunks, rag_meta or [{}] * len(rag_chunks)), 1):
            source = meta.get("source", "Unknown source") if meta else "Unknown source"
            parts.append(f"\nExcerpt {i} (from {source}):")
            parts.append(chunk)
    
    return "\n".join(parts)


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


