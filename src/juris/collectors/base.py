"""Abstract base collector interface and auto-discovery registry."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any, ClassVar

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

# ---------------------------------------------------------------------------
# Collector registry — populated automatically via __init_subclass__
# ---------------------------------------------------------------------------

_COLLECTOR_REGISTRY: dict[str, type[BaseCollector]] = {}


class BaseCollector(ABC):
    """Base class for all data source collectors.

    Concrete subclasses are automatically registered by source name when the
    class is defined.  To declare that a collector is the *preferred* provider
    for certain document types, set the ``preferred_for`` class variable::

        class MyCollector(BaseCollector):
            source = Source.MY_SOURCE
            supported_doc_types = [DocType.FOO, DocType.BAR]
            preferred_for = [DocType.FOO]
    """

    source: ClassVar[Source]
    supported_doc_types: ClassVar[list[DocType]]
    preferred_for: ClassVar[list[DocType]] = []
    _limiter: RateLimiter

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Only register concrete collectors (those without abstract methods).
        # Subclasses can set ``_skip_registration = True`` to opt out
        # (useful for test doubles that reuse an existing source name).
        if getattr(cls, "_skip_registration", False):
            return
        if not getattr(cls, "__abstractmethods__", set()):
            source_val = getattr(cls, "source", None)
            if source_val is not None:
                _COLLECTOR_REGISTRY[str(source_val)] = cls

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
            kwargs: dict[str, Any] = {
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
        **kwargs: Any,
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

                delay = self._backoff_base * (self._backoff_factor**attempt)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        delay = max(delay, float(retry_after))

                logger.warning(
                    "HTTP %d for %s, retrying in %.1fs (attempt %d/%d)",
                    resp.status_code,
                    url,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(delay)

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt == self._max_retries:
                    raise
                delay = self._backoff_base * (self._backoff_factor**attempt)
                logger.warning(
                    "%s for %s, retrying in %.1fs (attempt %d/%d)",
                    type(exc).__name__,
                    url,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(delay)

        # Should not be reached, but satisfy the type checker
        raise last_exc or httpx.HTTPError("All retries exhausted")

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
                            delay = self._backoff_base * (self._backoff_factor**attempt)
                            logger.warning(
                                "HTTP %d downloading %s, retrying in %.1fs",
                                resp.status_code,
                                url,
                                delay,
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
                    delay = self._backoff_base * (self._backoff_factor**attempt)
                    logger.warning(
                        "%s downloading %s, retrying in %.1fs",
                        type(e).__name__,
                        url,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
            except (httpx.HTTPError, OSError) as e:
                logger.warning("Failed to download %s: %s", url, e)
                return False

        logger.warning(
            "Failed to download %s after %d retries: %s",
            url,
            self._max_retries,
            last_exc,
        )
        return False

    async def download_attachments(self, doc: Document, base_dir: Path) -> Document:
        """Download PDF attachments and extract text from the primary one.

        Subclasses that need custom behaviour can override this method.
        """
        pdf_attachments = [a for a in doc.attachments if a.mime_type == "application/pdf"]
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


# ---------------------------------------------------------------------------
# Registry accessor functions
# ---------------------------------------------------------------------------

_discovery_done = False


def _ensure_discovered() -> None:
    """Import all collector modules so every subclass is registered.

    This is called lazily the first time a registry accessor is used,
    avoiding import-order problems when individual collector modules are
    imported directly (e.g. ``from juris.collectors.domstol import …``).
    """
    global _discovery_done  # noqa: PLW0603
    if _discovery_done:
        return
    _discovery_done = True

    import importlib
    import pkgutil
    from pathlib import Path

    pkg_dir = str(Path(__file__).resolve().parent)
    for info in pkgutil.iter_modules([pkg_dir]):
        if not info.name.startswith("_"):
            importlib.import_module(f"juris.collectors.{info.name}")


def get_registry() -> dict[str, type[BaseCollector]]:
    """Return a copy of the collector registry (source name -> class)."""
    _ensure_discovered()
    return dict(_COLLECTOR_REGISTRY)


def get_collector_class(source_name: str) -> type[BaseCollector]:
    """Get a collector class by source name.  Raises *KeyError* if unknown."""
    _ensure_discovered()
    return _COLLECTOR_REGISTRY[source_name]


def get_doc_type_providers() -> dict[str, list[str]]:
    """Map each doc-type value to the list of source names that support it."""
    _ensure_discovered()
    mapping: dict[str, list[str]] = {}
    for source_name, cls in _COLLECTOR_REGISTRY.items():
        for dt in cls.supported_doc_types:
            mapping.setdefault(dt.value, []).append(source_name)
    return mapping


def get_preferred_providers() -> dict[str, str]:
    """Build the preferred-provider map from collector declarations.

    Doc types with a single provider are automatically preferred.
    Explicit ``preferred_for`` declarations on collector classes override
    when multiple providers exist.
    """
    _ensure_discovered()
    doc_type_providers = get_doc_type_providers()

    # Default: sole-provider doc types get their only provider
    preferred: dict[str, str] = {
        dt: providers[0] for dt, providers in doc_type_providers.items() if len(providers) == 1
    }

    # Explicit overrides from collector classes
    for source_name, cls in _COLLECTOR_REGISTRY.items():
        for dt in cls.preferred_for:
            preferred[dt.value] = source_name

    return preferred
