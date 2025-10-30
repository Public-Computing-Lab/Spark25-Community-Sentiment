import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
import folium
from streamlit.components.v1 import html as st_html


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
        st.dataframe(rows, width='stretch')
    else:
        st.write("No rows returned.")
        # Show unique values if available
        unique_values = sql_result.get("unique_values", {})
        if unique_values:
            st.info("💡 **Available values in key columns:**")
            for col, vals in unique_values.items():
                with st.expander(f"View unique values in '{col}'"):
                    # Show as list or table
                    if len(vals) <= 20:
                        st.write(", ".join(str(v)[:100] for v in vals))
                    else:
                        st.write(f"Showing first 20 of {len(vals)} values:")
                        st.write(", ".join(str(v)[:100] for v in vals[:20]))
                        st.write(f"... and {len(vals) - 20} more")


def _render_map_from_result(result: Dict[str, Any], key_suffix: str = "") -> None:
    cols = result.get("columns", []) if isinstance(result, dict) else []
    rows = result.get("rows", []) if isinstance(result, dict) else []
    col_map = {c.lower(): c for c in cols}
    lat_col = col_map.get("latitude") or col_map.get("lat")
    lon_col = col_map.get("longitude") or col_map.get("lon")
    if not (lat_col and lon_col and rows):
        return
    st.subheader("Map (sample of points)")
    max_points = 500
    pts = []
    for r in rows[:max_points]:
        lat_raw = r.get(lat_col)
        lon_raw = r.get(lon_col)
        try:
            lat = float(lat_raw)
            lon = float(lon_raw)
        except Exception:
            continue
        if lat and lon:
            pts.append((lat, lon))
    if not pts:
        st.info("No valid latitude/longitude values in result to plot.")
        return
    avg_lat = sum(p[0] for p in pts) / len(pts)
    avg_lon = sum(p[1] for p in pts) / len(pts)
    fmap = folium.Map(location=[avg_lat, avg_lon], zoom_start=12)
    for lat, lon in pts:
        folium.CircleMarker(location=[lat, lon], radius=3, color="#2a7", fill=True, fill_opacity=0.7).add_to(fmap)
    st_html(fmap._repr_html_(), height=500)


def main() -> None:
    st.set_page_config(page_title="Conversational SQL + RAG Chatbot", layout="wide")
    _init_runtime()
    
    st.title("💬 Conversational SQL + RAG Chatbot")
    st.caption("Ask questions and have a conversation! The bot remembers our chat history.")
    _ensure_env()

    # Initialize conversation history in session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "conversation_history" not in st.session_state:
        st.session_state.conversation_history: List[Dict[str, str]] = []

    with st.sidebar:
        st.header("⚙️ Options")
        mode_choice = st.selectbox(
            "Answer mode",
            options=["auto", "rag", "sql", "hybrid"],
            index=3,  # Default to hybrid
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
        show_map = st.checkbox("Show map if latitude/longitude present", value=True)
        
        if st.button("🗑️ Clear Chat History", type="secondary"):
            st.session_state.messages = []
            st.session_state.conversation_history = []
            st.rerun()

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            # Show additional info if available
            if "sql" in message and message.get("show_sql") and message["sql"]:
                with st.expander("View SQL"):
                    st.code(message["sql"], language="sql")
                if "result" in message:
                    _display_sql_result(message["result"])
            # Always show unique values if available (even if SQL isn't shown)
            if "result" in message:
                result = message["result"]
                if isinstance(result, dict) and result.get("unique_values"):
                    unique_values = result.get("unique_values", {})
                    if unique_values:
                        with st.expander("💡 Available values in database columns"):
                            for col, vals in unique_values.items():
                                st.write(f"**{col}:**")
                                if len(vals) <= 20:
                                    st.write(", ".join(str(v)[:200] for v in vals))
                                else:
                                    st.write(", ".join(str(v)[:200] for v in vals[:20]))
                                    st.caption(f"... and {len(vals) - 20} more values")
            if "map" in message and message.get("show_map") and message.get("result"):
                _render_map_from_result(message["result"])
            if "sources" in message:
                with st.expander("Sources"):
                    for source in message["sources"]:
                        st.write(source)

    # Chat input
    if prompt := st.chat_input("Ask a question..."):
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    if mode_choice == "auto":
                        plan = uc._route_question(prompt)
                    else:
                        plan = _build_manual_plan(mode_choice, k, tags_raw, sources_raw)

                    mode = plan.get("mode", "rag")
                    
                    # Prepare conversation history (format: list of {"role": "user"/"assistant", "content": "..."})
                    conversation_history = st.session_state.conversation_history.copy()

                    if mode == "sql":
                        if not os.getenv("DATABASE_URL"):
                            st.error("DATABASE_URL not set. SQL mode unavailable.")
                            response_text = "DATABASE_URL not set. SQL mode unavailable."
                        else:
                            out = uc._run_sql(prompt, conversation_history)
                            response_text = out.get("answer", "")
                            
                            # Store message with metadata
                            assistant_msg = {
                                "role": "assistant",
                                "content": response_text,
                                "sql": out.get("sql", ""),
                                "result": out.get("result", {}),
                                "show_sql": show_sql,
                                "show_map": show_map,
                            }
                            
                            if show_sql:
                                with st.expander("View SQL"):
                                    st.code(out.get("sql", ""), language="sql")
                                _display_sql_result(out.get("result", {}))
                            if show_map:
                                _render_map_from_result(out.get("result", {}), key_suffix="sql")

                    elif mode == "hybrid":
                        if not os.getenv("DATABASE_URL"):
                            st.info("DATABASE_URL not set. Running RAG-only.")
                            out = uc._run_rag(prompt, plan, conversation_history)
                            response_text = out.get("answer", "")
                            metas: List[Dict[str, Any]] = out.get("metadata", [])
                            
                            assistant_msg = {
                                "role": "assistant",
                                "content": response_text,
                                "sources": [m.get("source", "Unknown") for m in metas[:20]],
                            }
                            
                            if metas:
                                with st.expander("Sources"):
                                    for m in metas[:20]:
                                        st.write(m.get("source", "Unknown"))
                        else:
                            out = uc._run_hybrid(prompt, plan, conversation_history)
                            response_text = out.get("answer", "")
                            
                            sqlp = out.get("sql", {})
                            assistant_msg = {
                                "role": "assistant",
                                "content": response_text,
                                "sql": sqlp.get("sql", ""),
                                "result": sqlp.get("result", {}),
                                "show_sql": show_sql,
                                "show_map": show_map,
                            }
                            
                            if show_sql:
                                sqlp = out.get("sql", {})
                                with st.expander("View SQL"):
                                    st.code(sqlp.get("sql", ""), language="sql")
                                _display_sql_result(sqlp.get("result", {}))
                            if show_map:
                                sqlp = out.get("sql", {})
                                result = sqlp.get("result", {}) if isinstance(sqlp, dict) else {}
                                _render_map_from_result(result, key_suffix="hybrid")
                            
                            ragp = out.get("rag", {})
                            metas: List[Dict[str, Any]] = ragp.get("metadata", [])
                            if metas:
                                assistant_msg["sources"] = [m.get("source", "Unknown") for m in metas[:20]]
                                with st.expander("Sources"):
                                    for m in metas[:20]:
                                        st.write(m.get("source", "Unknown"))

                    else:  # rag
                        out = uc._run_rag(prompt, plan, conversation_history)
                        response_text = out.get("answer", "")
                        metas: List[Dict[str, Any]] = out.get("metadata", [])
                        
                        assistant_msg = {
                            "role": "assistant",
                            "content": response_text,
                            "sources": [m.get("source", "Unknown") for m in metas[:20]],
                        }
                        
                        if metas:
                            with st.expander("Sources"):
                                for m in metas[:20]:
                                    st.write(m.get("source", "Unknown"))

                    # Update conversation history for LLM context
                    st.session_state.conversation_history.append({"role": "user", "content": prompt})
                    st.session_state.conversation_history.append({"role": "assistant", "content": response_text})
                    
                    # Keep conversation history manageable (last 20 messages)
                    if len(st.session_state.conversation_history) > 20:
                        st.session_state.conversation_history = st.session_state.conversation_history[-20:]
                    
                    # Add assistant message to chat display
                    st.session_state.messages.append(assistant_msg)
                    
                    st.write(response_text)

                except Exception as exc:  # noqa: BLE001
                    error_msg = f"Error: {exc}"
                    st.error(error_msg)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_msg,
                    })


if __name__ == "__main__":
    main()

