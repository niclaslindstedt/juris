"""Shared helper for querying the EU Publications Office CELLAR SPARQL endpoint."""

from __future__ import annotations

import logging

import httpx

from juris.utils import RateLimiter

logger = logging.getLogger(__name__)

SPARQL_ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"

PAGE_SIZE = 50


async def sparql_query(
    client: httpx.AsyncClient,
    limiter: RateLimiter,
    query: str,
) -> list[dict[str, dict[str, str]]]:
    """Execute a SPARQL SELECT query and return the result bindings.

    Each binding is a dict mapping variable names to ``{"type": ..., "value": ...}``
    dicts as returned by the SPARQL JSON results format.
    """
    await limiter.wait()
    try:
        resp = await client.post(
            SPARQL_ENDPOINT,
            data={"query": query},
            headers={
                "Accept": "application/sparql-results+json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", {}).get("bindings", [])
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning("SPARQL query failed: %s", e)
        return []


def eurlex_html_url(celex: str, lang: str = "SV") -> str:
    """Build a EUR-Lex full-text HTML URL from a CELEX number."""
    return f"https://eur-lex.europa.eu/legal-content/{lang}/TXT/HTML/?uri=CELEX:{celex}"


def eurlex_url(celex: str) -> str:
    """Build a EUR-Lex document URL from a CELEX number."""
    return f"https://eur-lex.europa.eu/legal-content/SV/ALL/?uri=CELEX:{celex}"
