"""CJEU (Court of Justice of the EU) collector via CELLAR SPARQL endpoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import date, datetime

import httpx

from juris.collectors._cellar import PAGE_SIZE, eurlex_html_url, eurlex_url, sparql_query
from juris.collectors.base import BaseCollector
from juris.models import DocType, Document, Source
from juris.utils import RateLimiter, build_doc_id, html_to_text

logger = logging.getLogger(__name__)

_CJEU_QUERY_TEMPLATE = """\
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?celex ?title ?date ?ecli WHERE {{
  ?work cdm:resource_legal_id_celex ?celex .
  ?work cdm:work_date_document ?date .
  ?work cdm:work_has_resource-type
    <http://publications.europa.eu/resource/authority/resource-type/JUDG> .
  ?work cdm:case-law_delivered-by-court
    <http://publications.europa.eu/resource/authority/court/CJ> .
  {filters}
  OPTIONAL {{
    ?work cdm:work_has_expression ?expr .
    ?expr cdm:expression_uses_language
      <http://publications.europa.eu/resource/authority/language/SWE> .
    ?expr cdm:expression_title ?title_sv .
  }}
  OPTIONAL {{
    ?work cdm:work_has_expression ?expr_en .
    ?expr_en cdm:expression_uses_language
      <http://publications.europa.eu/resource/authority/language/ENG> .
    ?expr_en cdm:expression_title ?title_en .
  }}
  OPTIONAL {{ ?work cdm:case-law_ecli ?ecli . }}
  BIND(COALESCE(?title_sv, ?title_en, ?celex) AS ?title)
}}
ORDER BY DESC(?date)
LIMIT {limit}
OFFSET {offset}
"""


def _build_filters(
    since: date | None = None,
    until: date | None = None,
) -> str:
    """Build SPARQL FILTER clauses for date range."""
    parts: list[str] = []
    if since:
        parts.append(f'FILTER(?date >= "{since.isoformat()}"^^xsd:date)')
    if until:
        parts.append(f'FILTER(?date <= "{until.isoformat()}"^^xsd:date)')
    return "\n  ".join(parts)


def _binding_value(row: dict[str, dict[str, str]], key: str) -> str:
    """Extract a string value from a SPARQL result binding."""
    binding = row.get(key)
    if binding is None:
        return ""
    return binding.get("value", "")


class CjeuCollector(BaseCollector):
    """Collects CJEU judgments from the EU CELLAR SPARQL endpoint."""

    source = Source.CURIA
    supported_doc_types = [DocType.CJEU]

    def __init__(self, rate_limit: float = 1.0) -> None:
        self._limiter = RateLimiter(min_interval=rate_limit)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=60.0,
                headers={"User-Agent": "juris/0.1.0 (Swedish law data collector)"},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _parse_result(self, row: dict[str, dict[str, str]]) -> Document | None:
        """Map a SPARQL result row to a Document."""
        celex = _binding_value(row, "celex")
        if not celex:
            return None

        title = _binding_value(row, "title") or celex
        date_str = _binding_value(row, "date")
        ecli = _binding_value(row, "ecli")

        try:
            doc_date = date.fromisoformat(date_str) if date_str else date.today()
        except ValueError:
            doc_date = date.today()

        session = str(doc_date.year)
        designation = celex
        doc_id = build_doc_id(DocType.CJEU, designation, session)

        return Document(
            doc_id=doc_id,
            doc_type=DocType.CJEU,
            designation=designation,
            session=session,
            title=title,
            summary=ecli if ecli else None,
            date=doc_date,
            department="Court of Justice of the European Union",
            source=Source.CURIA,
            source_id=celex,
            source_url=eurlex_url(celex),
            fetched_at=datetime.now(),
        )

    async def _fetch_full_text(self, celex: str) -> str | None:
        """Fetch full text from EUR-Lex HTML page."""
        client = await self._get_client()
        await self._limiter.wait()
        # Try Swedish first, then English
        for lang in ("SV", "EN"):
            url = eurlex_html_url(celex, lang)
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 200 and len(resp.text) > 500:
                    return html_to_text(resp.text)
            except httpx.HTTPError:
                continue
        return None

    async def collect(
        self,
        doc_type: DocType,
        *,
        session: str | None = None,
        since: date | None = None,
        until: date | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Document]:
        """Yield CJEU judgments from the CELLAR SPARQL endpoint."""
        if doc_type != DocType.CJEU:
            raise ValueError(f"Unsupported doc type for CJEU: {doc_type}")

        # Convert session (year) to date range
        if session and not since and not until:
            try:
                year = int(session)
                since = date(year, 1, 1)
                until = date(year, 12, 31)
            except ValueError:
                pass

        filters = _build_filters(since, until)
        client = await self._get_client()
        count = 0
        offset = 0

        while True:
            query = _CJEU_QUERY_TEMPLATE.format(
                filters=filters,
                limit=PAGE_SIZE,
                offset=offset,
            )

            logger.info("CJEU SPARQL query offset=%d", offset)
            rows = await sparql_query(client, self._limiter, query)

            if not rows:
                break

            for row in rows:
                if limit and count >= limit:
                    return

                doc = self._parse_result(row)
                if not doc:
                    continue

                yield doc
                count += 1

            if len(rows) < PAGE_SIZE:
                break

            offset += PAGE_SIZE

    async def get_document(self, source_id: str) -> Document | None:
        """Fetch a single CJEU judgment by CELEX number."""
        client = await self._get_client()
        query = f"""\
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?celex ?title ?date ?ecli WHERE {{
  ?work cdm:resource_legal_id_celex "{source_id}" .
  ?work cdm:resource_legal_id_celex ?celex .
  ?work cdm:work_date_document ?date .
  OPTIONAL {{
    ?work cdm:work_has_expression ?expr .
    ?expr cdm:expression_uses_language
      <http://publications.europa.eu/resource/authority/language/SWE> .
    ?expr cdm:expression_title ?title_sv .
  }}
  OPTIONAL {{
    ?work cdm:work_has_expression ?expr_en .
    ?expr_en cdm:expression_uses_language
      <http://publications.europa.eu/resource/authority/language/ENG> .
    ?expr_en cdm:expression_title ?title_en .
  }}
  OPTIONAL {{ ?work cdm:case-law_ecli ?ecli . }}
  BIND(COALESCE(?title_sv, ?title_en, ?celex) AS ?title)
}} LIMIT 1"""

        rows = await sparql_query(client, self._limiter, query)
        if not rows:
            return None
        return self._parse_result(rows[0])
