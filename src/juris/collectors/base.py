"""Abstract base collector interface."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import httpx

from juris.models import DocType, Document, Source
from juris.pdf import extract_text as extract_pdf_text
from juris.storage import _doc_dir
from juris.utils import RateLimiter

logger = logging.getLogger(__name__)

USER_AGENT = "juris/0.1.0 (Swedish law data collector)"

# HTTP status codes that are considered transient and worth retrying
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Default retry configuration
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF_BASE = 1.0  # seconds
_DEFAULT_BACKOFF_FACTOR = 2.0


class BaseCollector(ABC):
    """Base class for all data source collectors."""

    source: Source
    supported_doc_types: list[DocType]
    _limiter: RateLimiter

    def __init__(
        self,
        rate_limit: float = 0.5,
        timeout: float = 30.0,
        follow_redirects: bool = False,
        base_url: str = "",
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
        backoff_factor: float = _DEFAULT_BACKOFF_FACTOR,
    ) -> None:
        self._limiter = RateLimiter(min_interval=rate_limit)
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout
        self._follow_redirects = follow_redirects
        self._base_url = base_url
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_factor = backoff_factor

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the HTTP client (creating it if needed)."""
        if self._client is None or self._client.is_closed:
            kwargs: dict = {
                "timeout": self._timeout,
                "headers": {"User-Agent": USER_AGENT},
                "follow_redirects": self._follow_redirects,
            }
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = httpx.AsyncClient(**kwargs)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _fetch_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        """Execute an HTTP request with retry and exponential backoff.

        Retries on transient HTTP errors (429, 5xx) and network timeouts.
        Respects Retry-After headers on 429 responses.

        Raises httpx.HTTPStatusError or httpx.HTTPError after all retries
        are exhausted.
        """
        client = await self._get_client()
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                await self._limiter.wait()
                resp = await client.request(method, url, **kwargs)

                if resp.status_code not in _RETRYABLE_STATUS_CODES:
                    resp.raise_for_status()
                    return resp

                # Retryable status — compute delay
                if attempt == self._max_retries:
                    resp.raise_for_status()
                    return resp  # unreachable, raise_for_status throws

                delay = self._backoff_base * (self._backoff_factor ** attempt)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        delay = max(delay, float(retry_after))

                logger.warning(
                    "HTTP %d for %s, retrying in %.1fs (attempt %d/%d)",
                    resp.status_code, url, delay, attempt + 1, self._max_retries,
                )
                await asyncio.sleep(delay)

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt == self._max_retries:
                    raise
                delay = self._backoff_base * (self._backoff_factor ** attempt)
                logger.warning(
                    "%s for %s, retrying in %.1fs (attempt %d/%d)",
                    type(exc).__name__, url, delay, attempt + 1, self._max_retries,
                )
                await asyncio.sleep(delay)

        # Should not be reached, but satisfy the type checker
        raise last_exc or httpx.HTTPError("All retries exhausted")  # type: ignore[arg-type]

    @abstractmethod
    def collect(
        self,
        doc_type: DocType,
        *,
        session: str | None = None,
        since: date | None = None,
        until: date | None = None,
        limit: int | None = None,
        skip_content: bool = False,
    ) -> AsyncIterator[Document]:
        """Yield documents matching the given criteria."""
        ...

    @abstractmethod
    async def get_document(self, source_id: str) -> Document | None:
        """Fetch a single document by its source-specific ID."""
        ...

    # ------------------------------------------------------------------
    # Shared attachment download + PDF extraction
    # ------------------------------------------------------------------

    async def _download_file(self, url: str, dest: Path, limiter: RateLimiter) -> bool:
        """Download a file via streaming with retry. Returns True on success."""
        client = await self._get_client()
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                await limiter.wait()
                dest.parent.mkdir(parents=True, exist_ok=True)
                async with client.stream("GET", url) as resp:
                    if resp.status_code in _RETRYABLE_STATUS_CODES:
                        if attempt < self._max_retries:
                            delay = self._backoff_base * (self._backoff_factor ** attempt)
                            logger.warning(
                                "HTTP %d downloading %s, retrying in %.1fs",
                                resp.status_code, url, delay,
                            )
                            await asyncio.sleep(delay)
                            continue
                    resp.raise_for_status()
                    with open(dest, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                return True
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_exc = e
                if attempt < self._max_retries:
                    delay = self._backoff_base * (self._backoff_factor ** attempt)
                    logger.warning(
                        "%s downloading %s, retrying in %.1fs",
                        type(e).__name__, url, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
            except (httpx.HTTPError, OSError) as e:
                logger.warning("Failed to download %s: %s", url, e)
                return False

        logger.warning(
            "Failed to download %s after %d retries: %s", url, self._max_retries, last_exc,
        )
        return False

    async def download_attachments(
        self, doc: Document, base_dir: Path
    ) -> Document:
        """Download PDF attachments and extract text from the primary one.

        Subclasses that need custom behaviour can override this method.
        """
        pdf_attachments = [
            a for a in doc.attachments if a.mime_type == "application/pdf"
        ]
        if not pdf_attachments:
            return doc

        limiter = self._limiter

        attach_dir = _doc_dir(base_dir, doc.doc_type, doc.session) / "attachments"
        primary_text: str | None = None

        for i, attachment in enumerate(pdf_attachments):
            dest = attach_dir / attachment.filename
            logger.info("Downloading PDF: %s", attachment.filename)

            if not await self._download_file(attachment.url, dest, limiter):
                continue

            rel_path = str(dest.relative_to(base_dir))
            attachment.local_path = rel_path

            # Extract text from the first (primary) PDF
            if i == 0:
                primary_text = extract_pdf_text(dest)
                if primary_text:
                    logger.info(
                        "Extracted %d chars from %s",
                        len(primary_text),
                        attachment.filename,
                    )

        # Prefer PDF text when it is substantially richer than scraped page text
        if primary_text:
            if not doc.text or len(primary_text) > len(doc.text) * 2:
                doc.text = primary_text

        return doc
