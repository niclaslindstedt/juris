"""ECtHR (European Court of Human Rights) collector via the HUDOC JSON API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import httpx

from juris.collectors.base import BaseCollector
from juris.models import DocType, Document, Source
from juris.utils import build_doc_id, html_to_text

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

    def __init__(self, rate_limit: float = 1.0) -> None:
        super().__init__(rate_limit=rate_limit)

    async def _search(
        self, query: str, start: int = 0, length: int = PAGE_SIZE
    ) -> list[dict]:
        """Execute a HUDOC search and return result items."""
        await self._limiter.wait()
        client = await self._get_client()
        try:
            resp = await client.get(
                SEARCH_URL,
                params={
                    "query": query,
                    "select": _SELECT,
                    "sort": "kpdate Descending",
                    "start": start,
                    "length": length,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning("HUDOC search failed: %s", e)
            return []

    def _parse_result(self, item: dict) -> Document | None:
        """Map a HUDOC result item to a Document."""
        columns = item.get("columns", {})
        item_id = columns.get("itemid", "")
        if not item_id:
            return None

        docname = columns.get("docname", "")
        appno = columns.get("appno", "")
        judgment_date_str = columns.get("judgmentdate", "")
        conclusion = columns.get("conclusion", "")
        article = columns.get("article", "")

        # Parse judgment date (format: "2023-01-15T00:00:00" or similar)
        try:
            doc_date = (
                date.fromisoformat(judgment_date_str[:10])
                if judgment_date_str
                else date.today()
            )
        except ValueError:
            doc_date = date.today()

        session = str(doc_date.year)

        # Use application number as designation, fallback to itemid
        designation = appno.split(";")[0].strip() if appno else item_id

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
        self, item_id: str,
    ) -> tuple[str | None, str | None]:
        """Try to fetch the full judgment HTML from the HUDOC conversion endpoint.

        HUDOC does not expose a public REST endpoint for full judgment text;
        the /app/conversion/ endpoint is often unavailable. When it fails we
        fall back to metadata-only collection. Returns (text, html) tuple.
        """
        await self._limiter.wait()
        client = await self._get_client()
        url = (
            "https://hudoc.echr.coe.int"
            f"/app/conversion/docx/html/body/{item_id}"
        )
        try:
            resp = await client.get(url)
            if resp.status_code == 200 and len(resp.text) > 200:
                raw_html = resp.text
                text = html_to_text(raw_html)
                return text, raw_html
        except httpx.HTTPError as e:
            logger.debug(
                "HUDOC full text unavailable for %s: %s", item_id, e,
            )
        return None, None

    async def collect(
        self,
        doc_type: DocType,
        *,
        session: str | None = None,
        since: date | None = None,
        until: date | None = None,
        limit: int | None = None,
        skip_content: bool = False,
    ) -> AsyncIterator[Document]:
        """Yield ECtHR judgments against Sweden from the HUDOC API."""
        if doc_type != DocType.ECHR:
            raise ValueError(f"Unsupported doc type for HUDOC: {doc_type}")

        # Convert session (year) to date range
        if session and not since and not until:
            try:
                year = int(session)
                since = date(year, 1, 1)
                until = date(year, 12, 31)
            except ValueError:
                pass

        query = _build_query(since, until)
        count = 0
        start = 0

        while True:
            logger.info("HUDOC search start=%d", start)
            results = await self._search(query, start=start, length=PAGE_SIZE)

            if not results:
                break

            for item in results:
                if limit and count >= limit:
                    return

                doc = self._parse_result(item)
                if not doc:
                    continue

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
