import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st


# Ensure repository-relative imports work
_THIS_FILE = Path(__file__).resolve()
_REAL_DIR = _THIS_FILE.parent
if str(_REAL_DIR) not in sys.path:
    sys.path.insert(0, str(_REAL_DIR))


import unified_chatbot as uc  # noqa: E402


def _init_runtime() -> None:
    uc._bootstrap_env()
    uc._fix_retrieval_vectordb_path()


def _parse_tags(raw: str) -> Optional[List[str]]:
    items = [x.strip() for x in (raw or "").split(",")]
    items = [x for x in items if x]
    return items or None


def _parse_sources(raw: str) -> Optional[List[str]]:
    lines = [(raw or "").strip().splitlines()]
    flat = [x.strip() for x in lines[0]] if lines else []
    flat = [x for x in flat if x]
    return flat or None


def _ensure_env() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        st.warning("OPENAI_API_KEY not set. Set it in your environment before asking.")
    if not os.getenv("DATABASE_URL"):
        st.info("DATABASE_URL not set. SQL/Hybrid modes will be disabled.")


def _build_manual_plan(mode: str, k: int, tags_raw: str, sources_raw: str) -> Dict[str, Any]:
    plan: Dict[str, Any] = {
        "mode": mode,
        "transcript_tags": _parse_tags(tags_raw),
        "policy_sources": _parse_sources(sources_raw),
        "k": k,
    }
    return plan


def _display_sql_result(sql_result: Dict[str, Any]) -> None:
    rows = sql_result.get("rows", []) if isinstance(sql_result, dict) else []
    if rows:
        st.dataframe(rows, use_container_width=True)
    else:
        st.write("No rows returned.")


def main() -> None:
    st.set_page_config(page_title="Unified SQL + RAG Chatbot", layout="wide")
    _init_runtime()

    st.title("Unified SQL + RAG Chatbot")
    _ensure_env()

    with st.sidebar:
        st.header("Options")
        mode_choice = st.selectbox(
            "Answer mode",
            options=["auto", "rag", "sql", "hybrid"],
            index=0,
            help="auto uses the router; others force a mode",
        )
        k = st.slider("RAG results (k)", min_value=1, max_value=10, value=5)
        tags_raw = st.text_input("Transcript tags (comma-separated)", placeholder="safety, media")
        sources_raw = st.text_area(
            "Policy sources (one per line)",
            placeholder="Boston Anti-Displacement Plan Analysis.txt\nBoston Slow Streets Plan Analysis.txt",
            height=80,
        )
        show_sql = st.checkbox("Show SQL and rows (when available)", value=False)

    question = st.text_area("Your question", height=100)
    ask = st.button("Ask", type="primary")

    if ask:
        if not question.strip():
            st.warning("Please enter a question.")
            return

        try:
            if mode_choice == "auto":
                plan = uc._route_question(question)
            else:
                plan = _build_manual_plan(mode_choice, k, tags_raw, sources_raw)

            st.caption(f"Routing plan: {plan}")
            mode = plan.get("mode", "rag")

            if mode == "sql":
                if not os.getenv("DATABASE_URL"):
                    st.error("DATABASE_URL not set. SQL mode unavailable.")
                    return
                out = uc._run_sql(question)
                st.subheader("Answer")
                st.write(out.get("answer", ""))
                if show_sql:
                    st.subheader("SQL")
                    st.code(out.get("sql", ""), language="sql")
                    st.subheader("Rows")
                    _display_sql_result(out.get("result", {}))

            elif mode == "hybrid":
                if not os.getenv("DATABASE_URL"):
                    st.info("DATABASE_URL not set. Running RAG-only.")
                    out = uc._run_rag(question, plan)
                    st.subheader("Answer")
                    st.write(out.get("answer", ""))
                    metas: List[Dict[str, Any]] = out.get("metadata", [])
                    if metas:
                        st.subheader("Sources")
                        for m in metas[:20]:
                            st.write(m.get("source", "Unknown"))
                else:
                    out = uc._run_hybrid(question, plan)
                    st.subheader("Answer")
                    st.write(out.get("answer", ""))
                    if show_sql:
                        sqlp = out.get("sql", {})
                        st.subheader("SQL")
                        st.code(sqlp.get("sql", ""), language="sql")
                        st.subheader("Rows")
                        _display_sql_result(sqlp.get("result", {}))
                    ragp = out.get("rag", {})
                    metas: List[Dict[str, Any]] = ragp.get("metadata", [])
                    if metas:
                        st.subheader("Sources")
                        for m in metas[:20]:
                            st.write(m.get("source", "Unknown"))

            else:  # rag
                out = uc._run_rag(question, plan)
                st.subheader("Answer")
                st.write(out.get("answer", ""))
                metas: List[Dict[str, Any]] = out.get("metadata", [])
                if metas:
                    st.subheader("Sources")
                    for m in metas[:20]:
                        st.write(m.get("source", "Unknown"))

        except Exception as exc:  # noqa: BLE001
            st.error(f"Error: {exc}")


if __name__ == "__main__":
    main()


