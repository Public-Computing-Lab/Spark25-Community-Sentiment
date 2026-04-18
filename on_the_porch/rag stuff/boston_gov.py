"""
Utilities for fetching AI search answers from Boston.gov.

This module supports the chatbot fallback flow by querying Boston.gov's
AI-enabled search page and extracting only the AI answer block.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma  # type: ignore
from langchain_core.documents import Document

from retrieval import GeminiEmbeddings


BOSTON_GOV_SEARCH_BASE_URL = "https://www.boston.gov/search"
BOSTON_GOV_SOURCE_LABEL = "Boston.gov"
BOSTON_GOV_SEARCH_PARAMS = {
    "source": "ai-enabled-search-menu",
    "referrer": "node/16575796",
    "language": "en",
    "anonymous": "true",
}
DEFAULT_TIMEOUT = 20
DEFAULT_VECTORDB_DIR = (Path(__file__).resolve().parent / "../vectordb_new").resolve()
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


def _stable_boston_gov_doc_id(question: str, answer: str) -> str:
    raw = f"BostonGov::{question.strip()}::{answer.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _ensure_dorchester_in_query(question: str) -> str:
    normalized = _clean_text(question)
    if not normalized:
        return "Dorchester Boston"
    lowered = normalized.lower()
    if "dorchester" in lowered:
        return normalized
    return f"{normalized} Dorchester Boston"


def _extract_boston_gov_ai_answer(html_text: str) -> Dict[str, List[Dict[str, str]] | List[str]]:
    soup = BeautifulSoup(html_text, "html.parser")
    summary_section = soup.select_one(
        "section.results-summary-wrapper.results_summary__AISearch"
    )
    if not summary_section:
        return {
            "paragraphs": [],
            "bullet_points": [],
            "links": [],
        }

    return {
        "paragraphs": [
            _clean_text(p.get_text(" ", strip=True))
            for p in summary_section.select("p")
            if _clean_text(p.get_text(" ", strip=True))
        ],
        "bullet_points": [
            _clean_text(li.get_text(" ", strip=True))
            for li in summary_section.select("li")
            if _clean_text(li.get_text(" ", strip=True))
        ],
        "links": [
            {
                "text": _clean_text(a.get_text(" ", strip=True)),
                "href": a.get("href", "").strip(),
            }
            for a in summary_section.select("a[href]")
            if a.get("href")
        ],
    }


def get_boston_gov_ai_answer(question: str) -> Dict[str, List[Dict[str, str]] | List[str] | str]:
    final_query = _ensure_dorchester_in_query(question)
    search_params = {
        "searchbar": final_query,
        **BOSTON_GOV_SEARCH_PARAMS,
    }
    search_url = f"{BOSTON_GOV_SEARCH_BASE_URL}?{urlencode(search_params)}"
    print(
        "  🏛️ Boston.gov fallback: starting live scrape "
        f"url={search_url} "
        f"question={question!r} "
        f"final_query={final_query!r}"
    )
    try:
        response = requests.get(
            search_url,
            timeout=DEFAULT_TIMEOUT,
            headers=DEFAULT_HEADERS,
        )
        response.raise_for_status()
    except Exception as exc:
        print(f"⚠️ Warning: Boston.gov fallback search request failed: {exc}")
        return []

    html_text = response.text or ""
    if not html_text:
        print("⚠️ Warning: Boston.gov fallback returned an empty search page.")
        return {
            "query": final_query,
            "paragraphs": [],
            "bullet_points": [],
            "links": [],
            "text": "",
        }

    data = _extract_boston_gov_ai_answer(html_text)
    paragraphs = data["paragraphs"]
    bullet_points = data["bullet_points"]
    links = data["links"]

    if not paragraphs and not bullet_points:
        print("⚠️ Warning: No AI search summary found")
    else:
        print(f"  🏛️ Boston.gov fallback: found AI summary from {BOSTON_GOV_SOURCE_LABEL}")
        for paragraph in paragraphs:
            print(f"     📄 {paragraph}")
        for bullet in bullet_points:
            print(f"     • {bullet}")

    text_parts: List[str] = []
    text_parts.extend(paragraphs)
    text_parts.extend(bullet_points)
    return {
        "query": final_query,
        "paragraphs": paragraphs,
        "bullet_points": bullet_points,
        "links": links,
        "text": "\n".join(text_parts).strip(),
    }


def add_boston_gov_answer_to_vectordb(
    question: str,
    answer: str,
    vectordb_dir: Path | None = None,
) -> str:
    """
    Add a Boston.gov-derived answer into the shared Chroma vector DB.

    The document is stored under source="BostonGov" so it can be retrieved later
    by the main RAG pipeline.
    """
    question = _clean_text(question)
    answer = (answer or "").strip()
    if not answer:
        raise ValueError("Boston.gov answer text cannot be empty")

    vdb_path = (vectordb_dir or DEFAULT_VECTORDB_DIR).resolve()
    vdb_path.mkdir(parents=True, exist_ok=True)

    page_content_parts = []
    if question:
        page_content_parts.append(f"Question: {question}")
    page_content_parts.append(f"Answer: {answer}")
    page_content = "\n".join(page_content_parts)

    metadata = {
        "source": "BostonGov",
        "doc_type": "boston_gov_answer",
        "tags": "boston.gov",
        "question": question,
    }

    document = Document(page_content=page_content, metadata=metadata)
    doc_id = _stable_boston_gov_doc_id(question, answer)

    print(f"  💾 Boston.gov vectordb: saving answer under source=BostonGov id={doc_id}")
    embeddings = GeminiEmbeddings()
    vectordb = Chroma(
        persist_directory=str(vdb_path),
        embedding_function=embeddings,
    )
    vectordb.add_documents([document], ids=[doc_id])
    print(f"  ✅ Boston.gov vectordb: saved to {vdb_path}")
    return doc_id


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch Boston.gov AI search answers.")
    parser.add_argument("--query", help="Search query to run against boston.gov")
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.query:
        result = get_boston_gov_ai_answer(args.query)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    parser.error("Provide --query")


if __name__ == "__main__":
    main()
