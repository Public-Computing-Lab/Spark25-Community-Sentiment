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
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def looks_like_legal_notice(event: dict) -> bool:
    """True if event_name or raw_text matches known legal-notice phrasing."""
    blob = " ".join(str(event.get(k, "")) for k in ("event_name", "raw_text"))
    return bool(_LEGAL_NOTICE_RE.search(blob))


def parse_issue_date_from_url(issue_url: str):
    """Extract YYYY-MM-DD publication date from a DotNews issue URL."""
    match = _re.search(r"/(\d{4})/(\d{2})/(\d{2})/", issue_url)
    if not match:
        return None
    try:
        return datetime.strptime("-".join(match.groups()), "%Y-%m-%d").date()
    except ValueError:
        return None


def fetch_issue_urls():
    """Fetch DotNews print-issue URLs from newest to oldest."""
    inprint_url = "https://www.dotnews.com/inprint/"

    print(f"  ↪ Fetching {inprint_url}")
    try:
        r = _requests.get(inprint_url, timeout=30)
        print(r)
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

    issue_urls = []
    seen = set()
    for match in matches:
        issue_url = match[0]
        if issue_url not in seen:
            seen.add(issue_url)
            issue_urls.append(issue_url)
    return issue_urls


def filter_issue_urls_by_cutoff(issue_urls, cutoff_date):
    """Keep only issues published on or after the configured cutoff date."""
    if not cutoff_date:
        return issue_urls

    filtered = []
    for issue_url in issue_urls:
        issue_date = parse_issue_date_from_url(issue_url)
        if issue_date and issue_date >= cutoff_date:
            filtered.append(issue_url)

    print(
        f"  ↪ Applying DOTNEWS_CUTOFF_DATE={cutoff_date.isoformat()}: "
        f"keeping {len(filtered)} of {len(issue_urls)} issues"
    )
    return filtered


def _compute_issue_number(issue_date):
    """
    Estimate the Reporter's volume issue number for a given publication date.

    The Reporter is a weekly Thursday paper. Issue 1 of any year is the first
    Thursday issue in that year — this hits the right number for ~95% of
    issues we've seen and is good enough for a media-search query string,
    which the REST API matches as a substring anyway. Off-by-one is fine
    because we widen the search to {n-1, n, n+1}.
    """
    from datetime import date, timedelta

    # Find the first Thursday of issue_date.year
    first_day = date(issue_date.year, 1, 1)
    days_to_thu = (3 - first_day.weekday()) % 7  # Thursday = 3
    first_thursday = first_day + timedelta(days=days_to_thu)
    if issue_date < first_thursday:
        # January issue printed before first Thursday — treat as last year
        return None
    weeks = (issue_date - first_thursday).days // 7
    return weeks + 1


def _resolve_pdf_via_media_api(issue_date):
    """
    Strategy A: query WordPress's public media REST API for the issue.

    The Reporter occasionally skips print weeks (e.g. there is no REP-8_26
    between REP-7 and REP-9), so a date-derived issue number can be off by
    several. We probe a window and verify each candidate by checking that
    its upload date (item.date) is within ±10 days of the issue date.
    """
    if not issue_date:
        return None

    from datetime import datetime as _dt

    n = _compute_issue_number(issue_date)
    if not n:
        return None

    yy = str(issue_date.year)[-2:]
    # Match the wide, drift-tolerant window used in filename probing.
    candidates = [n - 1, n, n - 2, n + 1, n - 3, n + 2]

    for guess in candidates:
        if guess < 1:
            continue
        search_term = f"REP-{guess}_{yy}"
        api_url = (
            "https://www.dotnews.com/wp-json/wp/v2/media"
            f"?search={search_term}&per_page=10&media_type=file"
        )
        try:
            r = _requests.get(api_url, timeout=20)
            if r.status_code != 200:
                continue
            items = r.json()
        except Exception:
            continue

        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            src = item.get("source_url", "") or ""
            if not src.lower().endswith(".pdf"):
                continue

            filename = src.rsplit("/", 1)[-1].lower()
            if not filename.startswith(f"rep-{guess}_{yy}"):
                continue

            # Verify upload date matches the issue date. The API returns
            # an ISO-8601 timestamp in item.date.
            item_date_str = item.get("date") or item.get("date_gmt") or ""
            try:
                item_dt = _dt.fromisoformat(item_date_str.replace("Z", "+00:00")).date()
                delta_days = abs((item_dt - issue_date).days)
            except Exception:
                delta_days = None

            if delta_days is None or delta_days > 10:
                continue

            print(
                f"  ↪ Found PDF via WP media API "
                f"(search={search_term}, uploaded {item_date_str[:10]})"
            )
            return src
    return None


def _resolve_pdf_via_filename_guess(issue_date):
    """
    Strategy B: build candidate URLs and HEAD-probe them, picking the one
    whose Last-Modified header is closest to the issue date.

    Real-world filenames seen on dotnews.com (case + suffix variation):
        REP-6_26web.pdf      REP-9_26WEB.pdf
        REP-26_25-web.pdf    REP-33_25web_0.pdf

    The Reporter's volume-issue numbering is wobbly — they skip print weeks
    occasionally (no REP-8_26 exists between REP-7 and REP-9), so a
    date-derived issue number can be off by 1–2. We probe a small window
    in priority order: the most-likely combination first, then widen.

    Search has three phases (each phase early-exits on a Δ≤2 hit, which
    means same-week match):

      Phase 1: most-likely combo — exact issue month + most-common suffix
      Phase 2: same month + alternate suffixes
      Phase 3: nearby months + all suffixes (uploads sometimes land late)

    If after all phases the best match is more than 3 days from the issue
    date, we treat it as "no PDF available yet" and skip — better to come
    back next week than to ingest a neighboring issue's content.
    """
    if not issue_date:
        return None

    from datetime import datetime as _dt
    from email.utils import parsedate_to_datetime as _parsedate

    n = _compute_issue_number(issue_date)
    if not n:
        return None

    yy = str(issue_date.year)[-2:]
    yyyy = str(issue_date.year)
    issue_date_dt = _dt.combine(issue_date, _dt.min.time())

    # Order matters: most-frequently-seen suffix first.
    suffix_priority = ["web", "-web", "WEB", "_web", "web_0", "WEB_0"]

    # Most likely actual issue numbers, in order. We bias slightly toward
    # smaller numbers because skipped print weeks are more common than
    # double-prints.
    issue_priority = [n - 1, n, n - 2, n + 1, n - 3, n + 2]
    issue_priority = [i for i in issue_priority if i >= 1]

    same_month = [f"{issue_date.month:02d}"]
    nearby_months = []
    for offset in (1, -1, 2, -2, 3):
        m = issue_date.month + offset
        if 1 <= m <= 12:
            nearby_months.append(f"{m:02d}")

    candidates = []  # (delta_days, filename, url, last_modified)

    def probe(guess_n, mm, suffix):
        filename = f"REP-{guess_n}_{yy}{suffix}.pdf"
        url = f"https://www.dotnews.com/wp-content/uploads/{yyyy}/{mm}/{filename}"
        try:
            head = _requests.head(url, timeout=8, allow_redirects=True)
        except Exception:
            return None
        if head.status_code != 200:
            return None
        last_modified = head.headers.get("Last-Modified")
        if not last_modified:
            return None
        try:
            lm_dt = _parsedate(last_modified).replace(tzinfo=None)
            delta_days = abs((lm_dt - issue_date_dt).days)
        except Exception:
            return None
        return (delta_days, filename, url, last_modified)

    def best_so_far():
        return min(candidates, key=lambda c: c[0]) if candidates else None

    # Phase 1: same month, top suffix, all issue numbers.
    # This catches the common case in 1-6 HEAD requests.
    for guess_n in issue_priority:
        result = probe(guess_n, same_month[0], suffix_priority[0])
        if result:
            candidates.append(result)
            if result[0] <= 2:
                # Same-week upload — almost certainly the right PDF, stop.
                break

    if best_so_far() and best_so_far()[0] <= 2:
        pass  # phase 1 was decisive, skip further probes
    else:
        # Phase 2: same month, remaining suffixes.
        for guess_n in issue_priority:
            for suffix in suffix_priority[1:]:
                result = probe(guess_n, same_month[0], suffix)
                if result:
                    candidates.append(result)
                    if result[0] <= 2:
                        break
            if best_so_far() and best_so_far()[0] <= 2:
                break

    if best_so_far() and best_so_far()[0] <= 2:
        pass
    else:
        # Phase 3: nearby months (occasional late uploads end up in a different
        # month folder than the issue date).
        for mm in nearby_months:
            for guess_n in issue_priority:
                result = probe(guess_n, mm, suffix_priority[0])
                if result:
                    candidates.append(result)
                    if result[0] <= 2:
                        break
            if best_so_far() and best_so_far()[0] <= 2:
                break

    if not candidates:
        return None

    candidates.sort(key=lambda c: c[0])
    best_delta, best_filename, best_url, best_lm = candidates[0]

    if best_delta > 3:
        # Closest match is more than 3 days off — likely a neighboring issue's
        # PDF, not this one's. Skip rather than ingest the wrong content.
        print(
            f"  ↪ Skipping: closest PDF is {best_filename} (Δ={best_delta}d) "
            f"— probably a neighboring issue, not this one. Re-run when the "
            f"actual PDF is uploaded."
        )
        return None

    print(
        f"  ↪ Found PDF via filename probe ({best_filename}, "
        f"last-modified {best_lm}, Δ={best_delta}d)"
    )
    return best_url


def _resolve_embedded_pdf_url(media_src: str):
    """Decode the PDF URL out of a viewer iframe/embed src."""
    media_src = media_src.replace("&#038;", "&").replace("&amp;", "&")
    if "gview" in media_src and "url=" in media_src:
        url_match = _re.search(r"[?&]url=(.+?)(?:&|$)", media_src)
        if url_match:
            return _unquote(url_match.group(1))
    if "admin-ajax.php" in media_src and "file=" in media_src:
        parsed = _urlparse(media_src)
        params = _parse_qs(parsed.query)
        if "file" in params:
            return _unquote(params["file"][0])
    if media_src.lower().endswith(".pdf"):
        return media_src
    return None


def _extract_pdf_url(html: str, issue_url: str):
    """Find the PDF URL on a DotNews issue page across embed strategies.

    The site has shifted between several PDF embed plugins over time
    (Google gview iframes, admin-ajax viewer, PDF Embedder, EmbedPress,
    PDF Poster Gutenberg block, PDF.js Viewer). The current PDF Poster
    plugin loads URLs via JavaScript, so the URL isn't in the static
    HTML at all — for that case we hit the WordPress REST API and fall
    back to filename-guess HEAD probes.

    Strategies are tried in order from highest-signal to most permissive.
    """

    issue_date = parse_issue_date_from_url(issue_url)

    # Strategy A: WordPress REST media search (works for current PDF Poster setup)
    api_hit = _resolve_pdf_via_media_api(issue_date)
    if api_hit:
        return api_hit

    # Strategy 1: legacy iframe / embed src
    for tag in ("iframe", "embed"):
        m = _re.search(rf'<{tag}[^>]+src="([^"]+)"', html, _re.IGNORECASE)
        if m:
            url = _resolve_embedded_pdf_url(m.group(1))
            if url:
                print(f"  ↪ Found PDF via <{tag}> src")
                return url

    # Strategy 2: data-* attributes used by JS-rendered viewers
    for attr in ("data-url", "data-src", "data-pdf-url", "data-file", "data-pdf"):
        m = _re.search(rf'{attr}="([^"]+\.pdf[^"]*)"', html, _re.IGNORECASE)
        if m:
            print(f"  ↪ Found PDF via {attr} attribute")
            return m.group(1)

    # Strategy 3: PDF Poster Gutenberg block — JSON inside HTML comment
    pdfp_block = _re.search(
        r'wp:pdfp/pdf-poster\s+(\{.*?\})\s*-->',
        html,
        _re.IGNORECASE | _re.DOTALL,
    )
    if pdfp_block:
        for url_match in _re.finditer(r'"url"\s*:\s*"([^"]+)"', pdfp_block.group(1)):
            candidate = url_match.group(1).replace("\\/", "/")
            if ".pdf" in candidate.lower():
                print("  ↪ Found PDF via PDF Poster block JSON")
                return candidate

    # Strategy 4: any "url":"...pdf..." JSON pair anywhere in the page
    m = _re.search(r'"(?:url|file|pdfUrl|src)"\s*:\s*"([^"]+\.pdf[^"]*)"', html, _re.IGNORECASE)
    if m:
        print("  ↪ Found PDF via JSON url field")
        return m.group(1).replace("\\/", "/")

    # Strategy 5: any .pdf URL anywhere on the page
    m = _re.search(r'https?://[^\s"\'<>]+\.pdf[^\s"\'<>]*', html, _re.IGNORECASE)
    if m:
        print("  ↪ Found PDF via raw URL scan")
        return m.group(0)

    # Strategy B (last resort): construct candidate URLs and HEAD-probe
    guess_hit = _resolve_pdf_via_filename_guess(issue_date)
    if guess_hit:
        return guess_hit

    return None


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

    # Decode HTML entities once, up front, so all strategies see normal &.
    html = r.text.replace("&#038;", "&").replace("&amp;", "&")

    pdf_url = _extract_pdf_url(html, issue_url)

    if not pdf_url:
        print("  ✗ Could not locate PDF URL on issue page")
        # Debug aid: surface anything that looks PDF-shaped on the page, so the
        # next plugin migration is a one-line regex fix instead of a bug hunt.
        pdf_hits = _re.findall(r'[^\s"\'<>]{0,80}\.pdf[^\s"\'<>]{0,80}', html, _re.IGNORECASE)
        if pdf_hits:
            print(f"  ↪ (debug) .pdf substrings: {pdf_hits[:3]}")
        json_hits = _re.findall(r'"(?:url|file|pdfUrl|src)"\s*:\s*"[^"]{0,200}"', html)
        if json_hits:
            print(f"  ↪ (debug) JSON url fields: {json_hits[:3]}")
        block_hits = _re.findall(r'wp:pdfp/pdf-poster[^-]{0,300}', html, _re.IGNORECASE)
        if block_hits:
            print(f"  ↪ (debug) pdfp block snippet: {block_hits[0][:300]}")
        if not (pdf_hits or json_hits or block_hits):
            print("  ↪ (debug) no PDF markers present — viewer likely fully JS-rendered")
        return None

    # Normalize scheme / protocol-relative URLs.
    if pdf_url.startswith("//"):
        pdf_url = "https:" + pdf_url
    elif pdf_url.startswith("http://"):
        pdf_url = "https://" + pdf_url[7:]
    pdf_url = pdf_url.replace("&#038;", "&").replace("&amp;", "&")

    print(f"  ↪ PDF URL: {pdf_url}")

    try:
        pr = _requests.get(pdf_url, timeout=60, stream=True)
        pr.raise_for_status()
    except Exception as e:
        print(f"  ✗ Download failed: {e}")
        return None

    filename = Path(_urlparse(pdf_url).path).name or "dotnews_latest.pdf"
    filename = _re.sub(r'[<>:"/\\|?*]', "_", filename)
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
    """Download every DotNews print issue currently listed on the inprint page.

    Returns a list of (pdf_path, issue_date) tuples so the caller can pass
    accurate publication dates into Gemini context.
    """
    issue_urls = fetch_issue_urls()
    if not issue_urls:
        return []
    issue_urls = filter_issue_urls_by_cutoff(issue_urls, DOTNEWS_CUTOFF_DATE)
    if not issue_urls:
        print("  ✗ No print issues found on or after the configured cutoff date")
        return []

    downloaded = []
    total = len(issue_urls)
    for idx, issue_url in enumerate(issue_urls, start=1):
        print(f"📥 Downloading issue {idx}/{total}...")
        pdf_path = download_issue_pdf(issue_url, output_dir=output_dir)
        if pdf_path:
            issue_date = parse_issue_date_from_url(issue_url)
            downloaded.append((pdf_path, issue_date))
    return downloaded


REPO_ROOT = THIS_DIR.parent.parent
load_dotenv(REPO_ROOT / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
DOTNEWS_CUTOFF_DATE_RAW = os.environ.get("DOTNEWS_CUTOFF_DATE", "").strip()

DOTNEWS_CUTOFF_DATE = None
if DOTNEWS_CUTOFF_DATE_RAW:
    try:
        DOTNEWS_CUTOFF_DATE = datetime.strptime(DOTNEWS_CUTOFF_DATE_RAW, "%Y-%m-%d").date()
    except ValueError:
        print(
            "✗ Invalid DOTNEWS_CUTOFF_DATE in .env. Expected YYYY-MM-DD, "
            f"got: {DOTNEWS_CUTOFF_DATE_RAW}",
            file=sys.stderr,
        )
        sys.exit(1)

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


# Pages that contain events almost always include at least one of:
#   - a day-of-week ("Tuesday", "Wed", "Thurs.")
#   - a month name ("January", "Feb")
#   - a clock time ("7:00 PM", "10:30am")
#   - explicit calendar markers ("p.m.", "a.m.")
# Pages without any of these are feature articles / ads / opinion pages, and
# sending them to Gemini just burns latency for an empty result. This filter
# is intentionally generous — when in doubt, we still call Gemini.
_EVENT_HINT_RE = re.compile(
    r"\b("
    r"mon(day)?|tue(s|sday)?|wed(nesday)?|thu(r|rs|rsday)?|fri(day)?|sat(urday)?|sun(day)?"
    r"|jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|aug(ust)?"
    r"|sep(t|tember)?|oct(ober)?|nov(ember)?|dec(ember)?"
    r")\b"
    r"|\b\d{1,2}:\d{2}\s*(a\.?m\.?|p\.?m\.?)\b"
    r"|\b\d{1,2}\s*(a\.?m\.?|p\.?m\.?)\b",
    re.IGNORECASE,
)


def page_likely_has_events(page_text: str) -> bool:
    """Cheap regex pre-filter: does this page mention any date/time signals?"""
    if not page_text or len(page_text.strip()) < 50:
        return False
    return bool(_EVENT_HINT_RE.search(page_text))


def insert_events_to_db(events):
    if not events:
        return 0
    conn = get_db_connection()
    inserted = 0
    skipped = 0
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

                normalized = normalize_title(event_name)

                try:
                    cur.execute(
                        """
                        SELECT id FROM weekly_events
                        WHERE normalized_name = %s
                        AND (start_date <=> %s)
                        LIMIT 1
                        """,
                        (normalized, event.get("start_date")),
                    )
                    if cur.fetchone():
                        skipped += 1
                        continue
                except Exception as e:
                    print(f"    ⚠ Dedup check failed for '{event_name}': {e}")

                try:
                    cur.execute(
                        """
                        INSERT INTO weekly_events (
                            source_pdf, page_number, event_name, normalized_name, event_date,
                            start_date, end_date, start_time, end_time,
                            raw_text, category
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            event.get("source", "dotnews"),
                            event.get("page_number"),
                            event_name,
                            normalized,
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
    if skipped:
        print(f"  (skipped {skipped} already-present events)")
    return inserted


def process_pdf(pdf_path: Path, issue_date=None, page_workers: int = 5):
    """
    Process a single DotNews PDF.

    Args:
      pdf_path: PDF on disk.
      issue_date: Optional datetime.date for the publication date. If
        provided, takes precedence over filename/mtime parsing — this
        gives Gemini accurate date context (otherwise we fall back to
        the file's mtime, which can be off by weeks).
      page_workers: Concurrent Gemini calls per PDF. The free Gemini
        tier handles 5-10 fine; reduce if you hit rate limits.
    """
    print(f"📰 Got: {pdf_path.name}")

    if issue_date:
        pub_date = issue_date.strftime("%Y-%m-%d")
    else:
        mtime = datetime.fromtimestamp(pdf_path.stat().st_mtime)
        pub_date = extract_publication_date(pdf_path.name, mtime)
    print(f"📅 Publication date: {pub_date or '(unknown)'}")

    print("📖 Reading PDF pages...")
    pages = pdf_to_pages(pdf_path)
    print(f"   {len(pages)} pages extracted")

    # Pre-filter: skip pages with no event-like signals.
    candidate_pages = [
        (i, text) for i, text in enumerate(pages, start=1)
        if page_likely_has_events(text)
    ]
    skipped_pages = len(pages) - len(candidate_pages)
    if skipped_pages:
        print(f"   ↪ Pre-filter: skipping {skipped_pages} pages with no date/time signals")
    if not candidate_pages:
        print("⚠ No event-like content found on any page")
        return 0

    print(f"🔎 Extracting events from {len(candidate_pages)} candidate pages "
          f"(parallel, {page_workers} workers)...")

    all_events = []
    with ThreadPoolExecutor(max_workers=page_workers) as pool:
        futures = {
            pool.submit(extract_events_from_page, text, page_num, pdf_path.name, pub_date): page_num
            for page_num, text in candidate_pages
        }
        for fut in as_completed(futures):
            page_num = futures[fut]
            try:
                events = fut.result()
            except Exception as e:
                print(f"   ⚠ Page {page_num} failed: {e}")
                continue
            if events:
                print(f"   ✓ Page {page_num}: +{len(events)} events")
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

    # Parse --workers and --pdf-workers (both optional). These control the
    # two layers of parallelism: pages within a PDF, and PDFs in flight.
    page_workers = 5
    pdf_workers = 3
    cleaned = []
    i = 0
    while i < len(args):
        if args[i] == "--workers" and i + 1 < len(args):
            try:
                page_workers = max(1, int(args[i + 1]))
            except ValueError:
                pass
            i += 2
        elif args[i] == "--pdf-workers" and i + 1 < len(args):
            try:
                pdf_workers = max(1, int(args[i + 1]))
            except ValueError:
                pass
            i += 2
        else:
            cleaned.append(args[i])
            i += 1
    args = cleaned

    dotnews_dir = THIS_DIR / "temp_downloads" / "dotnews"
    dotnews_dir.mkdir(parents=True, exist_ok=True)

    if first_time:
        if args:
            print("✗ --first-time cannot be combined with a manual PDF path")
            return 1
        print("📥 First-time sync: downloading all DotNews newsletters...")
        downloaded = download_all_pdfs_v2(output_dir=dotnews_dir)
        if not downloaded:
            print("✗ Download failed or no newsletters were found")
            return 1

        print(
            f"\n🚀 Processing {len(downloaded)} PDFs "
            f"({pdf_workers} in parallel, {page_workers} pages/PDF)\n"
        )

        total_events = 0
        # Run PDFs in parallel. Each worker also fans out its pages internally,
        # so total concurrent Gemini calls ≈ pdf_workers × page_workers.
        with ThreadPoolExecutor(max_workers=pdf_workers) as pool:
            futures = {
                pool.submit(process_pdf, pdf_path, issue_date, page_workers): pdf_path
                for pdf_path, issue_date in downloaded
            }
            for fut in as_completed(futures):
                pdf_path = futures[fut]
                try:
                    total_events += fut.result()
                except Exception as e:
                    print(f"✗ {pdf_path.name}: {e}")

        print(
            f"\n✅ First-time sync complete: processed {len(downloaded)} PDFs, "
            f"extracted {total_events} events"
        )
        return 0

    if args:
        pdf_path = Path(args[0])
        if not pdf_path.exists():
            print(f"✗ File not found: {pdf_path}")
            return 1
        print(f"📄 Using provided PDF: {pdf_path}")
        process_pdf(pdf_path, page_workers=page_workers)
        return 0

    print("📥 Downloading latest newsletter from dotnews.com...")
    pdf_path = download_latest_pdf_v2(output_dir=dotnews_dir)
    if not pdf_path:
        print("✗ Download failed or no new PDF available")
        return 1

    process_pdf(pdf_path, page_workers=page_workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())