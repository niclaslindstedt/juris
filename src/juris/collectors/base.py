"""Abstract base collector interface."""

from __future__ import annotations

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
    ) -> None:
        self._limiter = RateLimiter(min_interval=rate_limit)
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout
        self._follow_redirects = follow_redirects
        self._base_url = base_url

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
        """Download a file via streaming. Returns True on success."""
        await limiter.wait()
        client = await self._get_client()
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
            return True
        except (httpx.HTTPError, OSError) as e:
            logger.warning("Failed to download %s: %s", url, e)
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
