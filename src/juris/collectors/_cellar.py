"""Shared helper for querying the EU Publications Office CELLAR SPARQL endpoint."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

import httpx

from juris.utils import html_to_text

if TYPE_CHECKING:
    from juris.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

SPARQL_ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"

PAGE_SIZE = 50


def binding_value(row: dict[str, dict[str, str]], key: str) -> str:
    """Extract a string value from a SPARQL result binding."""
    binding = row.get(key)
    if binding is None:
        return ""
    return binding.get("value", "")


def build_sparql_date_filters(
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


async def fetch_eurlex_text(
    collector: BaseCollector,
    celex: str,
) -> str | None:
    """Fetch full text from EUR-Lex HTML page with retry, trying Swedish then English."""
    for lang in ("SV", "EN"):
        url = eurlex_html_url(celex, lang)
        try:
            resp = await collector._fetch_with_retry("GET", url, follow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 500:
                return html_to_text(resp.text)
        except httpx.HTTPError:
            continue
    return None


async def sparql_query(
    collector: BaseCollector,
    query: str,
) -> list[dict[str, dict[str, str]]]:
    """Execute a SPARQL SELECT query with retry and return the result bindings.

    Each binding is a dict mapping variable names to ``{"type": ..., "value": ...}``
    dicts as returned by the SPARQL JSON results format.
    """
    try:
        resp = await collector._fetch_with_retry(
            "POST",
            SPARQL_ENDPOINT,
            data={"query": query},
            headers={
                "Accept": "application/sparql-results+json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        data = resp.json()
        result: list[dict[str, dict[str, str]]] = data.get("results", {}).get("bindings", [])
        return result
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning("SPARQL query failed: %s", e or type(e).__name__)
        return []


def eurlex_html_url(celex: str, lang: str = "SV") -> str:
    """Build a EUR-Lex full-text HTML URL from a CELEX number."""
    return f"https://eur-lex.europa.eu/legal-content/{lang}/TXT/HTML/?uri=CELEX:{celex}"


def eurlex_url(celex: str) -> str:
    """Build a EUR-Lex document URL from a CELEX number."""
    return f"https://eur-lex.europa.eu/legal-content/SV/ALL/?uri=CELEX:{celex}"
