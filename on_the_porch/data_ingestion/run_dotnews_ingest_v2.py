"""
Standalone dotnews newsletter ingester — bypasses broken venv packages.

Downloads the latest dotnews.com PDF, extracts events with Gemini directly,
and inserts them into weekly_events via pymysql. Avoids sql_chat.app4,
langsmith, langchain, chromadb, and opentelemetry entirely.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import pymysql
import google.generativeai as genai
from pypdf import PdfReader

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))
from dotnews_downloader import download_latest_pdf  # noqa: E402 (kept for reference)
import re as _re
import requests as _requests
from urllib.parse import urlparse as _urlparse, parse_qs as _parse_qs, unquote as _unquote

# ---- Legal notice filter -------------------------------------------------
# Dotnews publishes probate filings, licensing hearings, zoning notices, etc.
# mixed in with community events. These are not real community events and
# should not land in weekly_events. Filter applied both via the Gemini prompt
# (upstream) and a regex check on returned events (downstream safety net).
LEGAL_NOTICE_PATTERNS = [
    r"\bpetition for\b",
    r"\bwritten appearance\b",
    r"\bprobate\b",
    r"\bguardian(ship)?\b",
    r"\bconservator\b",
    r"\bestate of\b",
    r"\bforeclosure\b",
    r"\bmortgagee\b",
    r"\bliquor license\b",
    r"\blicensing board\b",
    r"\bzoning board\b",
    r"\bvariance\b",
    r"\bpublic notice\b",
    r"\blegal notice\b",
    r"\bdeadline to file\b",
    r"\bchange of occupancy\b",
    r"\bproposal to (erect|renovate|construct|extend|subdivide)\b",
]
_LEGAL_NOTICE_RE = re.compile("|".join(LEGAL_NOTICE_PATTERNS), re.IGNORECASE)


def looks_like_legal_notice(event: dict) -> bool:
    """True if event_name or raw_text matches known legal-notice phrasing."""
    blob = " ".join(str(event.get(k, "")) for k in ("event_name", "raw_text"))
    return bool(_LEGAL_NOTICE_RE.search(blob))

def fetch_issue_urls():
    """Fetch DotNews print-issue URLs from newest to oldest."""
    inprint_url = "https://www.dotnews.com/inprint/"

    print(f"  ↪ Fetching {inprint_url}")
    try:
        r = _requests.get(inprint_url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"  ✗ Could not fetch inprint page: {e}")
        return []

    # Print issue URLs look like: /YYYY/MM/DD/<3-4 letter month>-<day>/
    issue_pattern = _re.compile(
        r'href="(https://www\.dotnews\.com/(\d{4})/(\d{2})/(\d{2})/[a-z]{3,4}-\d{1,2}/)"'
    )
    matches = issue_pattern.findall(r.text)
    if not matches:
        print("  ✗ No print issue links found on inprint page")
        return []

    matches.sort(key=lambda m: (m[1], m[2], m[3]), reverse=True)
    return [match[0] for match in matches]


def download_issue_pdf(issue_url: str, output_dir: Path):
    """Download a single DotNews issue PDF from its issue page."""
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"  ↪ Issue page: {issue_url}")

    try:
        r = _requests.get(issue_url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"  ✗ Could not fetch issue page: {e}")
        return None

    iframe_match = _re.search(r'<iframe[^>]+src="([^"]+)"', r.text)
    if not iframe_match:
        print("  ✗ No iframe on issue page")
        return None

    iframe_src = iframe_match.group(1)
    # Decode HTML entities first (&#038; -> &, &amp; -> &)
    iframe_src = iframe_src.replace("&#038;", "&").replace("&amp;", "&")
    pdf_url = None
    if "gview" in iframe_src and "url=" in iframe_src:
        # Extract the url= param value (goes to end of string or next &)
        url_match = _re.search(r"[?&]url=(.+?)(?:&|$)", iframe_src)
        if url_match:
            pdf_url = _unquote(url_match.group(1))
    elif "admin-ajax.php" in iframe_src and "file=" in iframe_src:
        parsed = _urlparse(iframe_src)
        params = _parse_qs(parsed.query)
        if "file" in params:
            pdf_url = _unquote(params["file"][0])
    elif iframe_src.lower().endswith(".pdf"):
        pdf_url = iframe_src

    if not pdf_url:
        print(f"  ✗ Could not extract PDF URL from iframe: {iframe_src}")
        return None

    if pdf_url.startswith("//"):
        pdf_url = "https:" + pdf_url
    elif pdf_url.startswith("http://"):
        pdf_url = "https://" + pdf_url[7:]
    # Decode HTML entities like &#038;
    pdf_url = pdf_url.replace("&#038;", "&").replace("&amp;", "&")

    print(f"  ↪ PDF URL: {pdf_url}")

    try:
        pr = _requests.get(pdf_url, timeout=60, stream=True)
        pr.raise_for_status()
    except Exception as e:
        print(f"  ✗ Download failed: {e}")
        return None

    filename = Path(_urlparse(pdf_url).path).name or "dotnews_latest.pdf"
    filename = _re.sub(r"[<>:\"/\\|?*]", "_", filename)
    out_path = output_dir / filename
    if out_path.exists():
        print(f"  ↪ Already downloaded: {out_path}")
        return out_path

    with open(out_path, "wb") as f:
        for chunk in pr.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    with open(out_path, "rb") as f:
        if not f.read(4).startswith(b"%PDF"):
            print("  ✗ Downloaded file is not a valid PDF")
            out_path.unlink()
            return None

    print(f"  ✓ Saved: {out_path} ({out_path.stat().st_size // 1024} KB)")
    return out_path


def download_latest_pdf_v2(output_dir: Path):
    """Replacement scraper for dotnews.com's new (2026) Elementor-based site."""
    issue_urls = fetch_issue_urls()
    if not issue_urls:
        return None

    latest_url = issue_urls[0]
    print(f"  ↪ Latest print issue: {latest_url}")
    return download_issue_pdf(latest_url, output_dir=output_dir)


def download_all_pdfs_v2(output_dir: Path):
    """Download every DotNews print issue currently listed on the inprint page."""
    issue_urls = fetch_issue_urls()
    if not issue_urls:
        return []

    downloaded_paths = []
    total = len(issue_urls)
    for idx, issue_url in enumerate(issue_urls, start=1):
        print(f"📥 Downloading issue {idx}/{total}...")
        pdf_path = download_issue_pdf(issue_url, output_dir=output_dir)
        if pdf_path:
            downloaded_paths.append(pdf_path)
    return downloaded_paths

REPO_ROOT = THIS_DIR.parent.parent
load_dotenv(REPO_ROOT / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

if not GEMINI_API_KEY:
    print("✗ GEMINI_API_KEY not set in .env", file=sys.stderr)
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)


def get_db_connection():
    try:
        return pymysql.connect(
            host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
            port=int(os.environ.get("MYSQL_PORT", "3306")),
            user=os.environ.get("MYSQL_USER", "root"),
            password=os.environ.get("MYSQL_PASSWORD", ""),
            database=os.environ.get("MYSQL_DB", "sentiment_demo"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.Cursor,
            autocommit=True,
        )
    except Exception as exc:
        print(f"✗ MySQL connection failed: {exc}", file=sys.stderr)
        sys.exit(1)


def extract_publication_date(filename, file_mtime):
    patterns = [
        (r"(\d{4})-(\d{2})-(\d{2})", "ymd"),
        (r"(\d{2})/(\d{2})/(\d{4})", "mdy"),
        (r"(\d{4})(\d{2})(\d{2})", "ymd"),
        (r"(\d{2})_(\d{2})_(\d{4})", "mdy"),
    ]
    for pattern, order in patterns:
        m = re.search(pattern, filename)
        if not m:
            continue
        try:
            if order == "ymd":
                y, mo, d = m.groups()
            else:
                mo, d, y = m.groups()
            date_str = f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except (ValueError, IndexError):
            continue
    if file_mtime:
        return file_mtime.strftime("%Y-%m-%d")
    return None


def extract_events_from_page(page_text, page_num, source, publication_date):
    if not page_text or len(page_text.strip()) < 50:
        return []

    model = genai.GenerativeModel(GEMINI_MODEL)
    if len(page_text) > 8000:
        page_text = page_text[:8000] + "\n\n[... text truncated ...]"

    date_context = ""
    if publication_date:
        try:
            pub_dt = datetime.strptime(publication_date, "%Y-%m-%d")
            date_context = f"""
IMPORTANT DATE CONTEXT:
- Newsletter publication date: {publication_date} ({pub_dt.strftime('%A, %B %d, %Y')})
- Convert day-of-week references to exact YYYY-MM-DD dates.
- Events typically occur in the week following publication.
"""
        except Exception:
            pass

    prompt = f"""
You are reading PAGE {page_num} of a community newsletter.
{date_context}
Extract ALL events with their dates and times from this page.

CRITICAL: Convert day-of-week references (Monday, Tuesday, etc.) to EXACT dates
(YYYY-MM-DD) using the newsletter publication date as reference.

DO NOT EXTRACT any of the following — they are legal/administrative notices,
NOT community events:
- Probate / estate filings (wills, guardianship, conservatorship petitions)
- Foreclosure or mortgagee sale notices
- Liquor license hearings or licensing board applications
- Zoning board of appeal hearings, variance requests
- Public notices, legal notices, "written appearance" deadlines
- Change-of-occupancy proposals, building permit notices
- Any item whose purpose is legal compliance or filing deadlines rather
  than a community-attendable gathering

Only extract events a neighborhood resident could actually attend: meetings,
classes, workshops, performances, health clinics, tree lightings, job fairs,
community dinners, religious services, cleanups, etc.

Return ONLY valid JSON (no explanations, no markdown, no code fences):

[
  {{
    "event_name": "...",
    "event_date": "...",
    "start_date": "YYYY-MM-DD or null",
    "end_date": "YYYY-MM-DD or null",
    "start_time": "HH:MM or null",
    "end_time": "HH:MM or null",
    "raw_text": "...",
    "location": "... or null",
    "category": "... or null"
  }}
]

Field rules:
- event_name: Short descriptive name (REQUIRED)
- event_date: Date label as written (REQUIRED)
- start_date/end_date: ISO YYYY-MM-DD
- start_time/end_time: 24-hour HH:MM or null
- raw_text: Full description
- category: "Youth/Family", "Public Meeting", "Arts/Culture", "Health/Wellness",
  "Housing", "Safety", "Education", or "Other"

If NO events, return [].
Never invent information.

Page {page_num} text:
\"\"\"
{page_text}
\"\"\"
"""

    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0})
        text = (response.text or "").strip()
        if not text:
            return []

        if text.startswith("```"):
            text = text.strip("`").strip()
            lines = text.splitlines()
            if lines and lines[0].strip().lower() in ("json", "javascript"):
                text = "\n".join(lines[1:]).strip()

        m = re.search(r"\[[\s\S]*\]", text)
        if m:
            text = m.group(0)

        if not (text.startswith("[") or text.startswith("{")):
            return []

        raw_events = json.loads(text)
        if not isinstance(raw_events, list):
            return []

        validated = []
        for event in raw_events:
            if not isinstance(event, dict):
                continue
            for key in ("start_date", "end_date"):
                val = event.get(key)
                if val and str(val).strip().lower() not in ("null", "none", ""):
                    try:
                        datetime.strptime(str(val).strip(), "%Y-%m-%d")
                    except ValueError:
                        event[key] = None
                else:
                    event[key] = None
            for key in ("start_time", "end_time"):
                val = event.get(key)
                if val and str(val).strip().lower() not in ("null", "none", ""):
                    if not re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", str(val).strip()):
                        event[key] = None
                else:
                    event[key] = None
            event["source"] = source
            event["page_number"] = page_num
            if looks_like_legal_notice(event):
                continue
            validated.append(event)
        return validated

    except Exception as e:
        print(f"    ⚠ Error on page {page_num}: {e}")
        return []


def pdf_to_pages(pdf_path):
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def insert_events_to_db(events):
    if not events:
        return 0
    conn = get_db_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM weekly_events LIKE 'category'")
            if not cur.fetchone():
                try:
                    cur.execute("ALTER TABLE weekly_events ADD COLUMN category TEXT")
                    print("  ℹ Added 'category' column to weekly_events")
                except Exception as e:
                    print(f"  ⚠ Could not add category column: {e}")

            for event in events:
                event_name = (event.get("event_name") or "").strip()
                if not event_name:
                    continue
                event_date = (event.get("event_date") or "").strip()
                if not event_date:
                    event_date = event.get("start_date") or event.get("end_date") or "no info"
                try:
                    cur.execute(
                        """
                        INSERT INTO weekly_events (
                            source_pdf, page_number, event_name, event_date,
                            start_date, end_date, start_time, end_time,
                            raw_text, category
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            event.get("source", "dotnews"),
                            event.get("page_number"),
                            event_name,
                            event_date,
                            event.get("start_date"),
                            event.get("end_date"),
                            event.get("start_time"),
                            event.get("end_time"),
                            event.get("raw_text", ""),
                            event.get("category", "Other"),
                        ),
                    )
                    inserted += 1
                except Exception as e:
                    print(f"    ⚠ Could not insert '{event_name}': {e}")
    finally:
        conn.close()
    return inserted


def process_pdf(pdf_path: Path):
    print(f"📰 Got: {pdf_path.name}")

    mtime = datetime.fromtimestamp(pdf_path.stat().st_mtime)
    pub_date = extract_publication_date(pdf_path.name, mtime)
    print(f"📅 Publication date: {pub_date or '(unknown)'}")

    print("📖 Reading PDF pages...")
    pages = pdf_to_pages(pdf_path)
    print(f"   {len(pages)} pages extracted")

    all_events = []
    for i, page_text in enumerate(pages, start=1):
        if not page_text.strip():
            continue
        print(f"🔎 Extracting events from page {i}/{len(pages)}...")
        events = extract_events_from_page(page_text, i, pdf_path.name, pub_date)
        if events:
            print(f"   + {len(events)} events")
            all_events.extend(events)

    print(f"\n📊 Total extracted from {pdf_path.name}: {len(all_events)} events")

    if all_events:
        inserted = insert_events_to_db(all_events)
        print(f"✓ Inserted {inserted} events into weekly_events")
    else:
        print("⚠ No events extracted — PDF may not have a calendar section")

    return len(all_events)


def main():
    args = sys.argv[1:]
    first_time = "--first-time" in args
    args = [arg for arg in args if arg != "--first-time"]

    dotnews_dir = THIS_DIR / "temp_downloads" / "dotnews"
    dotnews_dir.mkdir(parents=True, exist_ok=True)

    if first_time:
        if args:
            print("✗ --first-time cannot be combined with a manual PDF path")
            return 1
        print("📥 First-time sync: downloading all DotNews newsletters...")
        pdf_paths = download_all_pdfs_v2(output_dir=dotnews_dir)
        if not pdf_paths:
            print("✗ Download failed or no newsletters were found")
            return 1

        total_events = 0
        for idx, pdf_path in enumerate(pdf_paths, start=1):
            print(f"\n===== Processing newsletter {idx}/{len(pdf_paths)} =====")
            total_events += process_pdf(pdf_path)

        print(f"\n✅ First-time sync complete: processed {len(pdf_paths)} PDFs, extracted {total_events} events")
        return 0

    if args:
        pdf_path = Path(args[0])
        if not pdf_path.exists():
            print(f"✗ File not found: {pdf_path}")
            return 1
        print(f"📄 Using provided PDF: {pdf_path}")
    else:
        print("📥 Downloading latest newsletter from dotnews.com...")
        pdf_path = download_latest_pdf_v2(output_dir=dotnews_dir)
        if not pdf_path:
            print("✗ Download failed or no new PDF available")
            return 1

    process_pdf(pdf_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
