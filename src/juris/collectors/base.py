"""Abstract base collector interface and auto-discovery registry."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any, ClassVar

import httpx

from juris import __version__
from juris.models import Attachment, DocType, Document, SearchResult, Source
from juris.pdf import extract_text as extract_pdf_text
from juris.storage import doc_dir
from juris.utils import RateLimiter

logger = logging.getLogger(__name__)

USER_AGENT = f"juris/{__version__} (Swedish law data collector)"

# HTTP status codes that are considered transient and worth retrying
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Network errors that are considered transient and worth retrying
_RETRYABLE_NETWORK_ERRORS: tuple[type[BaseException], ...] = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)

# Default retry configuration: keep retrying for up to an hour with a
# capped exponential backoff. ``max_retries`` defaults to effectively
# unlimited so the wall-clock ``retry_budget`` is what gates real runs;
# tests override ``max_retries`` to a small number for fast assertions.
_DEFAULT_MAX_RETRIES = sys.maxsize
_DEFAULT_BACKOFF_BASE = 1.0  # seconds
_DEFAULT_BACKOFF_FACTOR = 2.0
_DEFAULT_BACKOFF_CAP = 60.0  # seconds — never sleep longer than this between attempts
_DEFAULT_RETRY_BUDGET = 3600.0  # seconds — give up after this much total wall-clock time


def _describe_error(exc: BaseException | None) -> str:
    """Compact description of a fetch failure for log lines."""
    if exc is None:
        return "unknown error"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


class FetchBudgetExhausted(Exception):
    """Raised when a fetch keeps failing transiently past the retry budget.

    Deliberately *not* a subclass of ``httpx.HTTPError`` so that collectors
    which catch ``HTTPError`` to soften individual fetch failures still let
    this propagate up to the CLI, where it surfaces as a hard run failure.
    """

    def __init__(self, url: str, elapsed: float, last_error: BaseException) -> None:
        self.url = url
        self.elapsed = elapsed
        self.last_error = last_error
        super().__init__(
            f"Retry budget exhausted after {elapsed:.0f}s for {url}: "
            f"{type(last_error).__name__}: {last_error}"
        )


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
    supports_search: ClassVar[bool] = False
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
        backoff_cap: float = _DEFAULT_BACKOFF_CAP,
        retry_budget: float = _DEFAULT_RETRY_BUDGET,
    ) -> None:
        self._limiter = RateLimiter(min_interval=rate_limit)
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout
        self._follow_redirects = follow_redirects
        self._base_url = base_url
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_factor = backoff_factor
        self._backoff_cap = backoff_cap
        self._retry_budget = retry_budget
        self.total_available: int | None = None

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

    async def is_available(self) -> bool:
        """Quick health check — return True if the source is reachable.

        Default implementation assumes the source is available.  Collectors
        for sources with known intermittent outages should override this to
        perform a fast probe (and return ``False`` on failure) so that
        callers can skip them gracefully.
        """
        return True

    def _compute_backoff(self, retries_done: int) -> float:
        """Capped exponential backoff: base, base*factor, base*factor^2, ..., cap."""
        delay = self._backoff_base * (self._backoff_factor**retries_done)
        return min(delay, self._backoff_cap)

    async def _fetch_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute an HTTP request with retry and exponential backoff.

        Retries transient HTTP errors (429, 5xx) and network errors with a
        capped exponential backoff. Honours ``Retry-After`` on 429s and a
        wall-clock ``retry_budget`` so transient outages are waited out
        rather than skipped. ``max_retries`` is a separate per-call cap
        (effectively unbounded by default) so tests can pin a low value.

        Permanent failures (non-retryable 4xx) raise the underlying
        ``HTTPStatusError`` immediately, without retry.

        When the retry budget runs out (only relevant in real runs where
        ``max_retries`` is effectively infinite) this raises
        ``FetchBudgetExhausted`` so the caller's run fails loudly rather
        than silently returning empty results. When ``max_retries`` is
        reached first, the original transient exception is re-raised.
        """
        client = await self._get_client()
        start = time.monotonic()
        retries_done = 0
        last_exc: BaseException | None = None

        while True:
            retry_after_hint: float | None = None
            try:
                await self._limiter.wait()
                resp = await client.request(method, url, **kwargs)

                if resp.status_code not in _RETRYABLE_STATUS_CODES:
                    resp.raise_for_status()
                    return resp

                # Treat retryable status as a failure to retry.
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    last_exc = exc

                if resp.status_code == 429:
                    header = resp.headers.get("Retry-After")
                    if header and header.isdigit():
                        retry_after_hint = float(header)

            except _RETRYABLE_NETWORK_ERRORS as exc:
                last_exc = exc

            # Decide whether to retry.
            retries_done += 1
            if retries_done > self._max_retries:
                assert last_exc is not None
                raise last_exc

            elapsed = time.monotonic() - start
            delay = self._compute_backoff(retries_done - 1)
            if retry_after_hint is not None:
                delay = max(delay, retry_after_hint)

            if elapsed + delay > self._retry_budget:
                assert last_exc is not None
                raise FetchBudgetExhausted(url, elapsed, last_exc) from last_exc

            logger.warning(
                "%s for %s, retrying in %.1fs (attempt %d, %.0fs elapsed)",
                _describe_error(last_exc),
                url,
                delay,
                retries_done,
                elapsed,
            )
            await asyncio.sleep(delay)

    # ------------------------------------------------------------------
    # Convenience fetch helpers — override in subclasses for custom
    # error handling (e.g. tracking last error, different return types).
    # ------------------------------------------------------------------

    async def _fetch_html(self, url: str) -> str | None:
        """Fetch a URL via GET with retry and return the response text.

        Returns ``None`` on any HTTP or network error.
        """
        try:
            resp = await self._fetch_with_retry("GET", url)
            return resp.text
        except httpx.HTTPStatusError as e:
            logger.warning("Failed to fetch %s: HTTP %d", url, e.response.status_code)
            return None
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Failed to fetch %s: %s", url, type(e).__name__)
            return None

    async def _post_html(self, url: str, data: dict[str, str | list[str]]) -> str | None:
        """POST form data with retry and return the response text.

        Returns ``None`` on any HTTP or network error.
        """
        try:
            resp = await self._fetch_with_retry("POST", url, data=data)
            return resp.text
        except httpx.HTTPStatusError as e:
            logger.warning("Failed to POST %s: HTTP %d", url, e.response.status_code)
            return None
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Failed to POST %s: %s", url, type(e).__name__)
            return None

    # ------------------------------------------------------------------
    # Shared parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _session_to_date_range(
        session: str | None,
        since: date | None,
        until: date | None,
    ) -> tuple[date | None, date | None]:
        """Convert a year-string *session* to a ``(since, until)`` date range.

        If *session* is a valid year and both *since* and *until* are ``None``,
        returns ``(date(year, 1, 1), date(year, 12, 31))``.
        Otherwise returns ``(since, until)`` unchanged.
        """
        if session and not since and not until:
            try:
                year = int(session)
                return date(year, 1, 1), date(year, 12, 31)
            except ValueError:
                pass
        return since, until

    @staticmethod
    def _extract_summary(text: str) -> str | None:
        """Extract the first substantial paragraph from *text* as a summary.

        Splits on double-newlines and returns the first paragraph longer than
        60 characters, truncated to 500 characters.  Returns ``None`` if no
        qualifying paragraph is found.
        """
        import re

        for paragraph in re.split(r"\n{2,}", text):
            stripped = paragraph.strip()
            if len(stripped) > 60:
                return stripped[:500]
        return None

    @staticmethod
    def _extract_pdf_attachments(
        soup: "BeautifulSoup",  # type: ignore[name-defined]  # noqa: F821
        base_url: str,
    ) -> list[Attachment]:
        """Find PDF links in a BeautifulSoup tree and return Attachment objects.

        De-duplicates by resolved URL.  Only includes links whose resolved URL
        starts with *base_url* (to skip external document-reader services).
        """
        import re
        from urllib.parse import urljoin

        attachments: list[Attachment] = []
        seen_urls: set[str] = set()
        for pdf_link in soup.find_all("a", href=re.compile(r"\.pdf$", re.IGNORECASE)):
            href = pdf_link["href"]
            if not isinstance(href, str):
                continue
            pdf_url = urljoin(base_url, href)
            if not pdf_url.startswith(base_url):
                continue
            if pdf_url in seen_urls:
                continue
            seen_urls.add(pdf_url)
            filename = pdf_url.rsplit("/", 1)[-1]
            attachments.append(
                Attachment(
                    filename=filename,
                    url=pdf_url,
                    mime_type="application/pdf",
                )
            )
        return attachments

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
        offset: int = 0,
    ) -> AsyncIterator[Document]:
        """Yield documents matching the given criteria.

        When *offset* is non-zero, skip the first *offset* documents.
        Collectors should implement this efficiently by calculating the
        starting page from the offset.
        """
        ...

    @abstractmethod
    async def get_document(self, source_id: str) -> Document | None:
        """Fetch a single document by its source-specific ID."""
        ...

    async def search(
        self,
        query: str,
        *,
        doc_type: DocType | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search for documents via the provider API.

        Override in subclasses that support remote search.
        Raises NotImplementedError by default.
        """
        raise NotImplementedError(f"{self.source} does not support search")

    # ------------------------------------------------------------------
    # Shared attachment download + PDF extraction
    # ------------------------------------------------------------------

    async def _download_file(self, url: str, dest: Path, limiter: RateLimiter) -> bool:
        """Download a file via streaming with retry. Returns True on success.

        Retries transient failures with the same capped-backoff/budget
        policy as ``_fetch_with_retry``. Unlike that method, individual
        attachment failures are treated as soft: this returns ``False``
        when the budget runs out so the rest of the document still saves.

        Writes to a temporary file first and atomically renames on
        completion so that an interrupted download never leaves a
        partial file at *dest*.
        """
        import os
        import tempfile

        client = await self._get_client()
        start = time.monotonic()
        retries_done = 0
        last_exc: BaseException | None = None

        while True:
            retry_after_hint: float | None = None
            try:
                await limiter.wait()
                dest.parent.mkdir(parents=True, exist_ok=True)
                async with client.stream("GET", url) as resp:
                    if resp.status_code in _RETRYABLE_STATUS_CODES:
                        try:
                            resp.raise_for_status()
                        except httpx.HTTPStatusError as exc:
                            last_exc = exc
                        if resp.status_code == 429:
                            header = resp.headers.get("Retry-After")
                            if header and header.isdigit():
                                retry_after_hint = float(header)
                    else:
                        resp.raise_for_status()
                        fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
                        try:
                            with os.fdopen(fd, "wb") as f:
                                async for chunk in resp.aiter_bytes(chunk_size=65536):
                                    f.write(chunk)
                            os.replace(tmp, dest)
                        except BaseException:
                            try:
                                os.unlink(tmp)
                            except OSError:
                                pass
                            raise
                        return True
            except _RETRYABLE_NETWORK_ERRORS as exc:
                last_exc = exc
            except (httpx.HTTPError, OSError) as exc:
                logger.warning("Failed to download %s: %s", url, exc or type(exc).__name__)
                return False

            retries_done += 1
            if retries_done > self._max_retries:
                logger.warning(
                    "Failed to download %s after %d attempts: %s",
                    url,
                    retries_done,
                    _describe_error(last_exc),
                )
                return False

            elapsed = time.monotonic() - start
            delay = self._compute_backoff(retries_done - 1)
            if retry_after_hint is not None:
                delay = max(delay, retry_after_hint)

            if elapsed + delay > self._retry_budget:
                logger.warning(
                    "Retry budget exhausted downloading %s after %.0fs: %s",
                    url,
                    elapsed,
                    _describe_error(last_exc),
                )
                return False

            logger.warning(
                "%s downloading %s, retrying in %.1fs (attempt %d, %.0fs elapsed)",
                _describe_error(last_exc),
                url,
                delay,
                retries_done,
                elapsed,
            )
            await asyncio.sleep(delay)

    async def download_attachments(self, doc: Document, base_dir: Path) -> Document:
        """Download PDF attachments and extract text from the primary one.

        Subclasses that need custom behaviour can override this method.
        """
        pdf_attachments = [a for a in doc.attachments if a.mime_type == "application/pdf"]
        if not pdf_attachments:
            return doc

        limiter = self._limiter

        attach_dir = doc_dir(base_dir, doc.doc_type, doc.session) / "attachments"
        primary_text: str | None = None

        for i, attachment in enumerate(pdf_attachments):
            dest = attach_dir / attachment.filename
            logger.debug("Downloading PDF: %s", attachment.filename)

            if not await self._download_file(attachment.url, dest, limiter):
                continue

            rel_path = str(dest.relative_to(base_dir))
            attachment.local_path = rel_path

            # Extract text from the first (primary) PDF
            if i == 0:
                primary_text = extract_pdf_text(dest)
                if primary_text:
                    logger.debug(
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


def get_searchable_sources() -> list[str]:
    """Return source names for collectors that support search."""
    _ensure_discovered()
    return [name for name, cls in _COLLECTOR_REGISTRY.items() if cls.supports_search]


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
