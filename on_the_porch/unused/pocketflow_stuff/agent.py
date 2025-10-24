"""
Pocket Flow – Minimal NL → SQL Orchestrator

This file implements the smallest Pocket Flow-compliant pipeline focused only on
turning a user's natural language query into a single SELECT SQL statement.

Flow nodes (deterministic, explicit contracts):
- receive_query: http → request envelope
- query_analysis: llm_small → intent/entities/flags
- metadata_retrieval: metadata_store (from .txt JSON) → tables/columns, schema_hash
- sql_generation: llm_strong → single SELECT SQL (validated)
- respond: http_response → returns SQL payload

Environment (.env):
- OPENAI_API_KEY
- OPENAI_MODEL
- METADATA_FILE (path to JSON .txt containing tables/columns)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv  # type: ignore
from openai import OpenAI  # type: ignore


# ----------------------------- Utility structures -----------------------------


@dataclass
class Request:
    user_id: Optional[str]
    query_text: str
    locale: Optional[str]
    session_id: Optional[str]
    request_id: str
    received_at: str


class PocketFlowAgent:
    def __init__(self, metadata_file: Optional[Path] = None) -> None:
        load_dotenv()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.llm = OpenAI(api_key=self.openai_api_key)

        env_metadata = os.getenv("METADATA_FILE")
        self.metadata_file = Path(env_metadata) if env_metadata else (
            metadata_file if metadata_file is not None else (Path.cwd() / "pocketflow_stuff" / "metadata" / "schema.txt")
        )

    # ---------------------------- Public interface ----------------------------

    def handle_request(self, query_text: str, user_id: Optional[str] = None, locale: Optional[str] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
        request = self._receive_query(user_id=user_id, query_text=query_text, locale=locale, session_id=session_id)
        analysis = self._query_analysis(request)
        metadata = self._metadata_retrieval()
        sql_payload = self._sql_generation(request, analysis, metadata)
        return self._respond(sql_payload)

    # ------------------------------ Node: receive -----------------------------

    def _receive_query(self, user_id: Optional[str], query_text: str, locale: Optional[str], session_id: Optional[str]) -> Request:
        request = Request(
            user_id=user_id,
            query_text=query_text,
            locale=locale,
            session_id=session_id,
            request_id=str(uuid.uuid4()),
            received_at=datetime.utcnow().isoformat() + "Z",
        )
        return request

    # --------------------------- Node: query_analysis -------------------------

    def _query_analysis(self, request: Request) -> Dict[str, Any]:
        system = "You are a lightweight parser. Extract intent and entities from the user query."
        user = request.query_text
        instructions = "Return JSON with fields: intent, entities, date_ranges, summary_flag, limit. Ensure valid JSON only."

        completion = self.llm.chat.completions.create(
            model=self.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
                {"role": "system", "content": instructions},
            ],
            temperature=0.1,
        )
        text = completion.choices[0].message.content or "{}"
        parsed = json.loads(text)

        intent = parsed.get("intent")
        if intent not in ["aggregate", "timeseries", "slice", "count", "top_k"]:
            intent = "slice"

        return {
            "request_id": request.request_id,
            "intent": intent,
            "entities": parsed.get("entities", []),
            "date_ranges": parsed.get("date_ranges", []),
            "summary_flag": bool(parsed.get("summary_flag")),
            "limit": parsed.get("limit"),
            "raw_query_text": request.query_text,
        }

    # ------------------------ Node: metadata_retrieval ------------------------

    def _metadata_retrieval(self) -> Dict[str, Any]:
        raw = self.metadata_file.read_text(encoding="utf-8")
        data = json.loads(raw)
        tables = data["tables"] if isinstance(data, dict) and "tables" in data else data
        schema_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return {"tables": tables, "schema_hash": schema_hash}

    # -------------------------- Node: sql_generation --------------------------

    def _sql_generation(self, request: Request, analysis: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        tables_json = json.dumps(metadata.get("tables", []))
        raw_query = analysis.get("raw_query_text", request.query_text)
        limit = analysis.get("limit")

        system = (
            "You are a strict SQL generator. Produce a single executable SELECT statement that answers the user's question using the provided schema. Do not produce comments or extra text. If the schema cannot answer the query, return {\"error\":\"schema_mismatch\"}.\n"
            "CONTEXT: Use only one SELECT statement. Tables/columns are exactly as defined in the schema JSON."
        )
        user = f"SCHEMA_JSON: {tables_json}\nUSER_QUERY: {raw_query}"
        requirements = f"If a LIMIT is provided ({limit}), use it; otherwise include LIMIT 1000 or less."

        completion = self.llm.chat.completions.create(
            model=self.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
                {"role": "system", "content": requirements},
            ],
            temperature=0.1,
        )
        sql_text = (completion.choices[0].message.content or "").strip().strip("`")

        is_valid = self._is_single_select(sql_text)
        payload: Dict[str, Any] = {
            "request_id": request.request_id,
            "schema_hash": metadata.get("schema_hash"),
            "sql_text": sql_text,
            "is_valid_single_select": is_valid,
        }
        if not is_valid:
            payload["error"] = "not_single_select"
        return payload

    @staticmethod
    def _is_single_select(sql_text: str) -> bool:
        text = sql_text.strip().rstrip(";")
        return text.lower().startswith("select ") and ";" not in text

    # ----------------------------- Node: respond ------------------------------

    def _respond(self, sql_payload: Dict[str, Any]) -> Dict[str, Any]:
        return sql_payload


# ----------------------------------- CLI -------------------------------------


def run_interactive() -> None:
    agent = PocketFlowAgent()
    print("Pocket Flow (NL→SQL) ready. Type a question, or 'exit' to quit.")
    while True:
        q = input("\nQuery> ").strip()
        if not q or q.lower() in {"exit", "quit"}:
            break
        result = agent.handle_request(q)
        print("\n--- SQL Payload ---")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    run_interactive()


