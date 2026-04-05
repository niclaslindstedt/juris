"""Lagrummet collector for SFS documents (via data.riksdagen.se).

Collects Swedish statutes (Svensk författningssamling) using the Riksdagen
open data API.  The original Lagrummet RDF/Atom feeds are no longer
accessible, so we fall back to the same underlying data served by
data.riksdagen.se with doktyp=sfs.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from datetime import date, datetime

import httpx

from juris.collectors.base import BaseCollector
from juris.models import Attachment, DocType, Document, Source
from juris.utils import RateLimiter, build_doc_id, html_to_text

logger = logging.getLogger(__name__)

BASE_URL = "https://data.riksdagen.se"

_SFS_PATTERN = re.compile(r"^(\d{4}):(.+)$")


def _parse_sfs_beteckning(beteckning: str) -> tuple[str, str]:
    """Parse SFS beteckning '2026:306' into (year, number).

    Returns ("2026", "306") on match, ("", beteckning) otherwise.
    """
    m = _SFS_PATTERN.match(beteckning.strip())
    if m:
        return m.group(1), m.group(2)
    return "", beteckning


class LagrummetCollector(BaseCollector):
    """Collects SFS documents from the Riksdagen open data API."""

    source = Source.LAGRUMMET
    supported_doc_types = [DocType.SFS]

    def __init__(self, rate_limit: float = 0.5) -> None:
        self._limiter = RateLimiter(min_interval=rate_limit)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=30.0,
                headers={"User-Agent": "juris/0.1.0 (Swedish law data collector)"},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _fetch_json(self, url: str) -> dict | None:
        """Fetch a URL and return parsed JSON, or None on error."""
        await self._limiter.wait()
        client = await self._get_client()
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return None

    async def _fetch_document_html(self, dok_id: str) -> str | None:
        """Fetch the full HTML content for a document."""
        data = await self._fetch_json(f"{BASE_URL}/dokument/{dok_id}.json")
        if not data:
            return None
        doc_data = data.get("dokumentstatus", {}).get("dokument", {})
        return doc_data.get("html")

    def _parse_document(self, item: dict, full_html: str | None = None) -> Document:
        """Convert a Riksdagen API document item to a Document model."""
        dok_id = item.get("dok_id", item.get("id", ""))
        beteckning = item.get("beteckning", "")

        year, number = _parse_sfs_beteckning(beteckning)
        session = year or None
        designation = number
        doc_id = build_doc_id(DocType.SFS, designation, session)

        date_str = item.get("datum", "")
        doc_date = date.fromisoformat(date_str[:10]) if date_str else date.today()

        text = None
        html = full_html
        if html:
            text = html_to_text(html)

        attachments: list[Attachment] = []
        filbilaga = item.get("filbilaga")
        if filbilaga and isinstance(filbilaga, dict):
            fils = filbilaga.get("fil", [])
            if isinstance(fils, dict):
                fils = [fils]
            for fil in fils:
                if isinstance(fil, dict) and fil.get("url"):
                    attachments.append(
                        Attachment(
                            filename=fil.get("namn", ""),
                            url=fil["url"],
                            mime_type=fil.get("typ"),
                            size_bytes=int(fil["storlek"]) if fil.get("storlek") else None,
                        )
                    )

        return Document(
            doc_id=doc_id,
            doc_type=DocType.SFS,
            designation=designation,
            session=session,
            title=item.get("titel", ""),
            summary=item.get("summary") or item.get("undertitel") or None,
            text=text,
            html=html,
            date=doc_date,
            department=item.get("organ") or None,
            source=Source.LAGRUMMET,
            source_id=dok_id,
            source_url=f"{BASE_URL}/dokument/{dok_id}",
            fetched_at=datetime.now(),
            attachments=attachments,
        )

    async def collect(
        self,
        doc_type: DocType,
        *,
        session: str | None = None,
        since: date | None = None,
        until: date | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Document]:
        """Yield SFS documents from the Riksdagen API."""
        if doc_type != DocType.SFS:
            raise ValueError(f"LagrummetCollector only supports SFS, got: {doc_type}")

        page_size = 20
        count = 0

        params: dict[str, str] = {
            "doktyp": "sfs",
            "utformat": "json",
            "antal": str(page_size),
            "sida": "1",
            "sort": "datum",
            "sortorder": "desc",
        }

        # Map session (year) to date range
        if session:
            params["from"] = f"{session}-01-01"
            params["tom"] = f"{session}-12-31"
        # Explicit date filters override session-derived dates
        if since:
            params["from"] = since.isoformat()
        if until:
            params["tom"] = until.isoformat()

        url = f"{BASE_URL}/dokumentlista/?" + "&".join(f"{k}={v}" for k, v in params.items())

        while url:
            data = await self._fetch_json(url)
            if not data:
                break

            doc_list = data.get("dokumentlista", {})
            documents = doc_list.get("dokument", [])

            if not documents:
                break

            if isinstance(documents, dict):
                documents = [documents]

            for item in documents:
                if limit and count >= limit:
                    return

                dok_id = item.get("dok_id", item.get("id", ""))
                logger.info("Fetching SFS %s: %s", item.get("beteckning", ""), item.get("titel", "")[:60])

                html = await self._fetch_document_html(dok_id)
                doc = self._parse_document(item, full_html=html)
                yield doc
                count += 1

            next_url = doc_list.get("@nasta_sida")
            if next_url and (not limit or count < limit):
                url = next_url
            else:
                break

    async def get_document(self, source_id: str) -> Document | None:
        """Fetch a single SFS document by its Riksdagen dok_id."""
        data = await self._fetch_json(f"{BASE_URL}/dokumentstatus/{source_id}.json")
        if not data:
            return None

        doc_data = data.get("dokumentstatus", {}).get("dokument", {})
        if not doc_data:
            return None

        html = doc_data.get("html")
        return self._parse_document(doc_data, full_html=html)
