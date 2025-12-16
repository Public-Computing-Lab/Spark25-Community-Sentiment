import os
from pathlib import Path

from pypdf import PdfReader
import google.generativeai as genai  # type: ignore


def _load_local_env() -> None:
    """
    Load environment variables from a .env file next to this script,
    following the same pattern as sql_chat/app4.py.
    """
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
        # Never break the script if .env loading fails
        pass


_load_local_env()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")


def _get_gemini_client():
    """
    Minimal Gemini client setup, following the pattern from sql_chat/app4.py.
    """
    api_key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    genai.configure(api_key=api_key)
    return genai


def main() -> None:
    # 1) Extract text from page 2 of the PDF (0-based index -> pages[1])
    reader = PdfReader("REP 46_25web.pdf")
    page2_text = reader.pages[1].extract_text() or ""

    # 2) Call Gemini the same way sql_chat does (GenerativeModel + generate_content)
    client = _get_gemini_client()
    model = client.GenerativeModel(GEMINI_MODEL)

    prompt = f"""
You are reading text extracted from page 2 of a PDF. It contains a box listing events happening throughout a week.

From the text below, extract ALL events and their dates.

Return ONLY plain text, one event per line, in this exact format:
EVENT_NAME | DATE

If you are unsure about a date, make a best-effort guess based on the text (e.g. 'Monday', 'June 3–5', etc.).
Do not add any explanations or extra text.

Text:
\"\"\"{page2_text}\"\"\"
"""

    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0},
    )

    # 3) Just print the LLM's response (event name + date per line)
    print((getattr(response, "text", "") or "").strip())


if __name__ == "__main__":
    main()
