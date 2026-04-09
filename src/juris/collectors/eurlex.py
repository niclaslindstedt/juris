"""EUR-Lex collector for EU regulations and directives via CELLAR SPARQL endpoint."""

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

# CELLAR resource-type URIs for regulations and directives
_RESOURCE_TYPES: dict[DocType, str] = {
    DocType.EU_REG: "http://publications.europa.eu/resource/authority/resource-type/REG",
    DocType.EU_DIR: "http://publications.europa.eu/resource/authority/resource-type/DIR",
}

_EURLEX_QUERY_TEMPLATE = """\
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?celex ?title ?date WHERE {{
  ?work cdm:resource_legal_id_celex ?celex .
  ?work cdm:work_date_document ?date .
  ?work cdm:work_has_resource-type <{resource_type}> .
  FILTER(!CONTAINS(STR(?celex), "R("))
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
  BIND(COALESCE(?title_sv, ?title_en, ?celex) AS ?title)
}}
ORDER BY DESC(?date)
LIMIT {limit}
OFFSET {offset}
"""


class EurLexCollector(BaseCollector):
    """Collects EU regulations and directives from the CELLAR SPARQL endpoint."""

    source = Source.EUR_LEX
    supported_doc_types = list(_RESOURCE_TYPES.keys())

    def __init__(self, rate_limit: float = 1.0) -> None:
        super().__init__(rate_limit=rate_limit, timeout=60.0)

    def _parse_result(self, row: dict[str, dict[str, str]], doc_type: DocType) -> Document | None:
        """Map a SPARQL result row to a Document."""
        celex = binding_value(row, "celex")
        if not celex:
            return None

        title = binding_value(row, "title") or celex
        date_str = binding_value(row, "date")

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
        doc_id = build_doc_id(doc_type, designation, session)

        label = "regulation" if doc_type == DocType.EU_REG else "directive"

        return Document(
            doc_id=doc_id,
            doc_type=doc_type,
            designation=designation,
            session=session,
            title=title,
            date=doc_date,
            department=f"European Union ({label})",
            source=Source.EUR_LEX,
            source_id=celex,
            source_url=eurlex_url(celex),
            fetched_at=datetime.now(tz=UTC),
        )

    async def _fetch_full_text(self, celex: str) -> str | None:
        """Fetch full text from EUR-Lex HTML page."""
        client = await self._get_client()
        return await fetch_eurlex_text(client, self._limiter, celex)

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
        """Yield EU regulations or directives from the CELLAR SPARQL endpoint."""
        if doc_type not in self.supported_doc_types:
            raise ValueError(f"Unsupported doc type for EUR-Lex: {doc_type}")

        resource_type = _RESOURCE_TYPES[doc_type]

        # Convert session (year) to date range
        if session and not since and not until:
            try:
                year = int(session)
                since = date(year, 1, 1)
                until = date(year, 12, 31)
            except ValueError:
                pass

        filters = build_sparql_date_filters(since, until)
        client = await self._get_client()
        count = 0
        sparql_offset = offset

        while True:
            query = _EURLEX_QUERY_TEMPLATE.format(
                resource_type=resource_type,
                filters=filters,
                limit=PAGE_SIZE,
                offset=sparql_offset,
            )

            logger.debug("EUR-Lex SPARQL query for %s offset=%d", doc_type.value, sparql_offset)
            rows = await sparql_query(client, self._limiter, query)

            if not rows:
                break

            for row in rows:
                if limit and count >= limit:
                    return

                doc = self._parse_result(row, doc_type)
                if not doc:
                    continue

                if not skip_content and doc.source_id:
                    text = await self._fetch_full_text(doc.source_id)
                    if text:
                        doc.text = text

                yield doc
                count += 1

            if len(rows) < PAGE_SIZE:
                break

            sparql_offset += PAGE_SIZE

    async def get_document(self, source_id: str) -> Document | None:
        """Fetch a single EU document by CELEX number."""
        client = await self._get_client()
        query = f"""\
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?celex ?title ?date ?restype WHERE {{
  ?work cdm:resource_legal_id_celex "{source_id}" .
  ?work cdm:resource_legal_id_celex ?celex .
  ?work cdm:work_date_document ?date .
  ?work cdm:work_has_resource-type ?restype .
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
  BIND(COALESCE(?title_sv, ?title_en, ?celex) AS ?title)
}} LIMIT 1"""

        rows = await sparql_query(client, self._limiter, query)
        if not rows:
            return None

        # Determine doc_type from the resource-type URI
        restype = binding_value(rows[0], "restype")
        reverse_map = {v: k for k, v in _RESOURCE_TYPES.items()}
        doc_type = reverse_map.get(restype, DocType.EU_REG)

        return self._parse_result(rows[0], doc_type)
