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


class BaseCollector(ABC):
    """Base class for all data source collectors."""

    source: Source
    supported_doc_types: list[DocType]

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

    @abstractmethod
    async def _get_client(self) -> httpx.AsyncClient:
        """Return the HTTP client (creating it if needed)."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the HTTP client."""
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

        # Get the rate limiter — subclasses store it as _limiter
        limiter: RateLimiter = getattr(self, "_limiter", RateLimiter())

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

        # Only overwrite text if the document didn't already have content
        if primary_text and not doc.text:
            doc.text = primary_text

        return doc
