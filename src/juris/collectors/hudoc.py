"""ECtHR (European Court of Human Rights) collector via the HUDOC JSON API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any

import httpx

from juris.collectors.base import BaseCollector
from juris.models import DocType, Document, SearchResult, Source
from juris.utils import build_doc_id

logger = logging.getLogger(__name__)

SEARCH_URL = "https://hudoc.echr.coe.int/app/query/results"
PAGE_SIZE = 20

# Fields to request from the HUDOC API
_SELECT = (
    "itemid,docname,appno,conclusion,importance,"
    "originatingbody,respondent,kpdate,judgmentdate,doctype,"
    "article,scl,languageisocode"
)


def _build_query(
    since: date | None = None,
    until: date | None = None,
) -> str:
    """Build a HUDOC query string for Swedish ECtHR judgments."""
    parts = [
        'contentsitename:"ECHR"',
        'documentcollectionid:"JUDGMENTS"',
        'respondent:"SWE"',
    ]
    if since:
        parts.append(f'kpdate>="{since.isoformat()}T00:00:00.0Z"')
    if until:
        parts.append(f'kpdate<="{until.isoformat()}T23:59:59.0Z"')
    return " AND ".join(parts)


class HudocCollector(BaseCollector):
    """Collects ECtHR judgments from the HUDOC search API."""

    source = Source.HUDOC
    supported_doc_types = [DocType.ECHR]
    supports_search = True

    def __init__(self, rate_limit: float = 1.0) -> None:
        super().__init__(rate_limit=rate_limit)

    async def _search(
        self,
        query: str,
        start: int = 0,
        length: int = PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        """Execute a HUDOC search with retry and return result items."""
        try:
            resp = await self._fetch_with_retry(
                "GET",
                SEARCH_URL,
                params={
                    "query": query,
                    "select": _SELECT,
                    "sort": "kpdate Descending",
                    "start": start,
                    "length": length,
                },
            )
            data = resp.json()
            results: list[dict[str, Any]] = data.get("results", [])
            return results
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning("HUDOC search failed: %s", e or type(e).__name__)
            return []

    def _parse_result(self, item: dict[str, Any]) -> Document | None:
        """Map a HUDOC result item to a Document."""
        columns = item.get("columns", {})
        item_id = columns.get("itemid", "")
        if not item_id:
            return None

        docname = columns.get("docname", "")
        appno = columns.get("appno", "")
        judgment_date_str = columns.get("judgmentdate", "")
        kp_date_str = columns.get("kpdate", "")
        conclusion = columns.get("conclusion", "")
        article = columns.get("article", "")

        # Parse judgment date (format: "2023-01-15T00:00:00" or similar).
        # Fall back to kpdate (publication date) when judgmentdate is absent.
        date_str = judgment_date_str or kp_date_str
        try:
            if date_str:
                doc_date = date.fromisoformat(date_str[:10])
            else:
                logger.warning("No judgment or publication date for %s, using today", item_id)
                doc_date = date.today()
        except ValueError:
            logger.warning(
                "Could not parse date '%s' for %s, using today",
                date_str,
                item_id,
            )
            doc_date = date.today()

        session = str(doc_date.year)

        # Use application number as designation, fallback to itemid.
        # Multiple HUDOC items can share the same appno (e.g. chamber vs
        # grand chamber), so append a short itemid suffix to disambiguate.
        base_appno = appno.split(";")[0].strip() if appno else ""
        designation = base_appno or item_id

        doc_id = build_doc_id(DocType.ECHR, designation, session)

        # Build a summary from conclusion and article
        summary_parts: list[str] = []
        if conclusion:
            summary_parts.append(conclusion)
        if article:
            summary_parts.append(f"Articles: {article}")
        summary = "; ".join(summary_parts) if summary_parts else None

        return Document(
            doc_id=doc_id,
            doc_type=DocType.ECHR,
            designation=designation,
            session=session,
            title=docname or designation,
            summary=summary,
            date=doc_date,
            department="European Court of Human Rights",
            source=Source.HUDOC,
            source_id=item_id,
            source_url=f"https://hudoc.echr.coe.int/eng?i={item_id}",
            fetched_at=datetime.now(tz=UTC),
        )

    async def _fetch_full_text(
        self,
        item_id: str,
    ) -> tuple[str | None, str | None]:
        """Try to fetch the full judgment text from HUDOC.

        Attempts multiple endpoints and languages in order:
        1. Swedish translation via HUDOC language-specific endpoint
        2. English HTML conversion (default)
        3. French HTML conversion (many ECHR judgments are in French)
        4. PDF conversion as final fallback

        Returns (text, html) tuple, or (None, None) if all fail.
        """
        client = await self._get_client()

        # PDF conversion endpoint (the HTML conversion endpoint is no longer available)
        await self._limiter.wait()
        pdf_url = f"https://hudoc.echr.coe.int/app/conversion/pdf/?library=ECHR&id={item_id}"
        try:
            resp = await client.get(pdf_url)
            if resp.status_code == 200 and len(resp.content) > 500:
                from juris.pdf import extract_text_from_bytes

                pdf_text = extract_text_from_bytes(resp.content)
                if pdf_text and len(pdf_text) > 100:
                    logger.debug("Extracted %d chars from HUDOC PDF for %s", len(pdf_text), item_id)
                    return pdf_text, None
        except httpx.HTTPError as e:
            logger.debug("HUDOC PDF unavailable for %s: %s", item_id, e)

        logger.debug("HUDOC full text unavailable for %s", item_id)
        return None, None

    async def search(
        self,
        query: str,
        *,
        doc_type: DocType | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search HUDOC for ECtHR judgments matching the query."""
        if doc_type and doc_type != DocType.ECHR:
            return []

        hudoc_query = f'contentsitename:"ECHR" AND documentcollectionid:"JUDGMENTS" AND "{query}"'
        raw_results = await self._search(hudoc_query, start=0, length=limit)

        results: list[SearchResult] = []
        for item in raw_results:
            doc = self._parse_result(item)
            if not doc:
                continue
            results.append(
                SearchResult(
                    doc_id=doc.doc_id,
                    doc_type=DocType.ECHR,
                    title=doc.title,
                    designation=doc.designation,
                    session=doc.session,
                    date=doc.date,
                    source=Source.HUDOC,
                    source_url=doc.source_url,
                    summary=doc.summary,
                )
            )

        return results

    async def collect(
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
        """Yield ECtHR judgments against Sweden from the HUDOC API."""
        if doc_type != DocType.ECHR:
            raise ValueError(f"Unsupported doc type for HUDOC: {doc_type}")

        # Convert session (year) to date range
        since, until = self._session_to_date_range(session, since, until)

        query = _build_query(since, until)
        count = 0
        start = offset

        seen_doc_ids: set[str] = set()

        while True:
            logger.debug("HUDOC search start=%d", start)
            results = await self._search(query, start=start, length=PAGE_SIZE)

            if not results:
                break

            for item in results:
                if limit and count >= limit:
                    return

                doc = self._parse_result(item)
                if not doc:
                    continue

                # Disambiguate when multiple HUDOC items share the same appno
                if doc.doc_id in seen_doc_ids and doc.source_id:
                    # Use last 6 chars of item_id for compact disambiguation
                    suffix = doc.source_id[-6:] if len(doc.source_id) > 6 else doc.source_id
                    designation = f"{doc.designation}-{suffix}"
                    doc.designation = designation
                    doc.doc_id = build_doc_id(DocType.ECHR, doc.designation, doc.session)
                seen_doc_ids.add(doc.doc_id)

                if not skip_content and doc.source_id:
                    text, html = await self._fetch_full_text(doc.source_id)
                    if text:
                        doc.text = text
                    if html:
                        doc.html = html

                yield doc
                count += 1

            if len(results) < PAGE_SIZE:
                break

            start += PAGE_SIZE

    async def get_document(self, source_id: str) -> Document | None:
        """Fetch a single ECtHR judgment by HUDOC item ID."""
        query = f'contentsitename:"ECHR" AND itemid:"{source_id}"'
        results = await self._search(query, start=0, length=1)
        if not results:
            return None
        return self._parse_result(results[0])
