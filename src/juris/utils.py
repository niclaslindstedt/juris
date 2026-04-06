"""Shared utilities: rate limiting, text extraction, ID construction."""

from __future__ import annotations

import asyncio
import re
import time
from datetime import date

from bs4 import BeautifulSoup, Tag

from juris.models import DocType

# Swedish month names for date parsing
_SWEDISH_MONTHS: dict[str, int] = {
    "januari": 1,
    "februari": 2,
    "mars": 3,
    "april": 4,
    "maj": 5,
    "juni": 6,
    "juli": 7,
    "augusti": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}


class RateLimiter:
    """Enforces minimum delay between requests."""

    def __init__(self, min_interval: float = 0.5) -> None:
        self._min_interval = min_interval
        self._last_request: float = 0

    async def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()


def parse_swedish_date(text: str) -> date | None:
    """Parse a Swedish date string like '02 april 2026' into a date object."""
    m = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", text)
    if not m:
        return None
    day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    month = _SWEDISH_MONTHS.get(month_name)
    if not month:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def extract_page_content(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """Extract main content text and HTML from a web page.

    Looks for <article>, <div role="main">, <main>, or content-like divs.
    Removes navigation, header, aside, and footer elements.
    Returns (text, html) tuple.
    """
    content_el = (
        soup.find("article")
        or soup.find("div", attrs={"role": "main"})
        or soup.find("main")
        or soup.find("div", class_=re.compile(r"content|entry|body", re.I))
    )
    if content_el and isinstance(content_el, Tag):
        for unwanted in content_el.find_all(["nav", "header", "aside", "footer"]):
            unwanted.decompose()
        html_str = str(content_el)
        return html_to_text(html_str), html_str
    body = soup.find("body")
    if body and isinstance(body, Tag):
        html_str = str(body)
        return html_to_text(html_str), html_str
    return None, None


def html_to_text(html: str) -> str:
    """Extract clean plain text from HTML."""
    soup = BeautifulSoup(html, "lxml")
    # Remove script and style elements
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_doc_id(doc_type: DocType, designation: str, session: str | None = None) -> str:
    """Build a canonical document ID.

    Examples:
        build_doc_id(DocType.PROP, "208", "2024/25") -> "prop-2024/25:208"
        build_doc_id(DocType.SOU, "42", "2024") -> "sou-2024:42"
    """
    if session:
        return f"{doc_type.value}-{session}:{designation}"
    return f"{doc_type.value}-{designation}"


def sanitize_filename(doc_id: str) -> str:
    """Convert a doc_id to a safe filename (no slashes or colons).

    Examples:
        "prop-2024/25:208" -> "prop-2024-25_208"
    """
    return doc_id.replace("/", "-").replace(":", "_")
