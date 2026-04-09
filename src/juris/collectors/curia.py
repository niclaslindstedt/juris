"""CJEU (Court of Justice of the EU) collector via CELLAR SPARQL endpoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

from juris.collectors._cellar import (
    PAGE_SIZE,
    binding_value,
    build_sparql_date_filters,
    eurlex_url,
    fetch_eurlex_text,
    sparql_query,
)
from juris.collectors.base import BaseCollector
from juris.models import DocType, Document, Source
from juris.utils import build_doc_id

logger = logging.getLogger(__name__)

_CJEU_QUERY_TEMPLATE = """\
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?celex ?title ?date ?ecli WHERE {{
  ?work cdm:resource_legal_id_celex ?celex .
  ?work cdm:work_date_document ?date .
  ?work cdm:work_has_resource-type
    <http://publications.europa.eu/resource/authority/resource-type/JUDG> .
  FILTER(CONTAINS(STR(?celex), "CJ"))
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


class CjeuCollector(BaseCollector):
    """Collects CJEU judgments from the EU CELLAR SPARQL endpoint."""

    source = Source.CURIA
    supported_doc_types = [DocType.CJEU]

    def __init__(self, rate_limit: float = 1.0) -> None:
        super().__init__(rate_limit=rate_limit, timeout=60.0)

    def _parse_result(self, row: dict[str, dict[str, str]]) -> Document | None:
        """Map a SPARQL result row to a Document."""
        celex = binding_value(row, "celex")
        if not celex:
            return None

        title = binding_value(row, "title") or celex
        date_str = binding_value(row, "date")
        ecli = binding_value(row, "ecli")

        try:
            if date_str:
                doc_date = date.fromisoformat(date_str)
            else:
                logger.warning("No date for CELEX %s, using today", celex)
                doc_date = date.today()
        except ValueError:
            logger.warning("Could not parse date '%s' for CELEX %s, using today", date_str, celex)
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
            date=doc_date,
            department="Court of Justice of the European Union",
            source=Source.CURIA,
            source_id=ecli or celex,
            source_url=eurlex_url(celex),
            fetched_at=datetime.now(tz=UTC),
        )

    async def _fetch_full_text(self, celex: str) -> str | None:
        """Fetch full text from EUR-Lex HTML page."""
        return await fetch_eurlex_text(self, celex)

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
        """Yield CJEU judgments from the CELLAR SPARQL endpoint."""
        if doc_type != DocType.CJEU:
            raise ValueError(f"Unsupported doc type for CJEU: {doc_type}")

        # Convert session (year) to date range
        since, until = self._session_to_date_range(session, since, until)

        filters = build_sparql_date_filters(since, until)
        count = 0
        sparql_offset = offset

        while True:
            query = _CJEU_QUERY_TEMPLATE.format(
                filters=filters,
                limit=PAGE_SIZE,
                offset=sparql_offset,
            )

            logger.debug("CJEU SPARQL query offset=%d", sparql_offset)
            rows = await sparql_query(self, query)

            if not rows:
                break

            for row in rows:
                if limit and count >= limit:
                    return

                doc = self._parse_result(row)
                if not doc:
                    continue

                if not skip_content and doc.designation:
                    text = await self._fetch_full_text(doc.designation)
                    if text:
                        doc.text = text
                        if not doc.summary:
                            doc.summary = self._extract_summary(text)

                yield doc
                count += 1

            if len(rows) < PAGE_SIZE:
                break

            sparql_offset += PAGE_SIZE

    async def get_document(self, source_id: str) -> Document | None:
        """Fetch a single CJEU judgment by CELEX number."""
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

        rows = await sparql_query(self, query)
        if not rows:
            return None
        return self._parse_result(rows[0])
