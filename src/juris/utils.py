"""Shared utilities: rate limiting, text extraction, ID construction."""

from __future__ import annotations

import asyncio
import re
import time

from bs4 import BeautifulSoup

from juris.models import DocType


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
