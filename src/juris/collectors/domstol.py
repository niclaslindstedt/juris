"""Domstolsverket rättspraxis API collector (rattspraxis.etjanst.domstol.se)."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from juris.collectors.base import BaseCollector
from juris.models import Attachment, DocType, Document, Source
from juris.utils import build_doc_id, html_to_text


def _strip_court_header(text: str) -> str:
    """Remove the standard court letterhead from the start of extracted PDF text.

    Matches the block from "Dok.Id" through "Sida N (M)" that Swedish courts
    embed in every PDF (address, phone, opening hours, etc.).
    """
    m = re.match(
        r"Dok\.Id\s+\d+\s.*?Sida\s+\d+\s*\(\d+\)\s*",
        text,
        re.DOTALL,
    )
    if m:
        return text[m.end() :].lstrip()
    return text


logger = logging.getLogger(__name__)

BASE_URL = "https://rattspraxis.etjanst.domstol.se"

# Mapping from DocType to Domstolsverket court code
_COURT_MAP: dict[DocType, str] = {
    DocType.NJA: "HDO",  # Högsta domstolen
    DocType.AD: "ADO",  # Arbetsdomstolen
    DocType.HFD: "HFD",  # Högsta förvaltningsdomstolen
    DocType.MOD: "MOD",  # Mark- och miljööverdomstolen
    DocType.PMOD: "PMOD",  # Patent- och marknadsöverdomstolen
}

# Regex to parse NJA references like "NJA 2025:19" or "NJA 2025 s. 283"
_NJA_REF_RE = re.compile(r"NJA\s+(\d{4})(?::|\s+s\.\s*)(\d+)")

# Regex to parse AD references like "AD 2025 nr 19"
_AD_REF_RE = re.compile(r"AD\s+(\d{4})\s+nr\s+(\d+)")

# Regex to parse HFD references like "HFD 2021 ref. 56" or legacy "RÅ 2010 ref. 19"
_HFD_REF_RE = re.compile(r"(?:HFD|RÅ)\s+(\d{4})\s+ref\.\s*(\d+)")

# Regex to parse MÖD references like "MÖD 2011:26"
_MOD_REF_RE = re.compile(r"MÖD\s+(\d{4}):(\d+)")

PAGE_SIZE = 20


def _parse_nja_reference(referat_list: list[str]) -> tuple[str, str | None]:
    """Extract (designation, session) from NJA reference strings.

    Tries formats like "NJA 2025:19" or "NJA 2025 s. 283".
    Prefers the "NJA YYYY:N" format (short reference) over page references.
    Returns ("", None) if no match.
    """
    # First pass: prefer "NJA YYYY:N" format
    for ref in referat_list:
        m = re.match(r"NJA\s+(\d{4}):(\d+)$", ref.strip())
        if m:
            return m.group(2), m.group(1)

    # Second pass: accept "NJA YYYY s. N" format
    for ref in referat_list:
        m = _NJA_REF_RE.search(ref)
        if m:
            return m.group(2), m.group(1)

    return "", None


def _parse_ad_reference(referat_list: list[str]) -> tuple[str, str | None]:
    """Extract (designation, session) from AD reference strings.

    Parses formats like "AD 2025 nr 19".
    Returns ("", None) if no match.
    """
    for ref in referat_list:
        m = _AD_REF_RE.search(ref.strip())
        if m:
            return m.group(2), m.group(1)  # (nr, year)
    return "", None


def _parse_hfd_reference(referat_list: list[str]) -> tuple[str, str | None]:
    """Extract (designation, session) from HFD/RÅ reference strings.

    Parses formats like "HFD 2021 ref. 56" or legacy "RÅ 2010 ref. 19".
    Returns ("", None) if no match.
    """
    for ref in referat_list:
        m = _HFD_REF_RE.search(ref.strip())
        if m:
            return m.group(2), m.group(1)  # (ref number, year)
    return "", None


def _parse_mod_reference(referat_list: list[str]) -> tuple[str, str | None]:
    """Extract (designation, session) from MÖD reference strings.

    Parses formats like "MÖD 2011:26".
    Returns ("", None) if no match.
    """
    for ref in referat_list:
        m = _MOD_REF_RE.search(ref.strip())
        if m:
            return m.group(2), m.group(1)  # (number, year)
    return "", None


_REFERENCE_PARSERS: dict[DocType, Callable[[list[str]], tuple[str, str | None]]] = {
    DocType.NJA: _parse_nja_reference,
    DocType.AD: _parse_ad_reference,
    DocType.HFD: _parse_hfd_reference,
    DocType.MOD: _parse_mod_reference,
}


class DomstolCollector(BaseCollector):
    """Collects court decisions from the Domstolsverket rättspraxis API."""

    source = Source.DOMSTOL
    supported_doc_types = list(_COURT_MAP.keys())

    def __init__(self, rate_limit: float = 0.5) -> None:
        super().__init__(rate_limit=rate_limit, base_url=BASE_URL)

    async def _fetch_json(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """Fetch JSON from the API. Returns parsed JSON or None on error."""
        await self._limiter.wait()
        client = await self._get_client()
        try:
            resp = await client.get(path, params=params)
            resp.raise_for_status()
            result: list[dict[str, Any]] | dict[str, Any] = resp.json()
            return result
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Failed to fetch %s: %s", path, e or type(e).__name__)
            return None

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_publication(self, pub: dict[str, Any], doc_type: DocType) -> Document | None:
        """Map a PubliceringDTO dict to a Document."""
        referat_list: list[str] = pub.get("referatNummerLista", [])
        mal_list: list[str] = pub.get("malNummerLista", [])
        avgorandedatum: str = pub.get("avgorandedatum", "")

        # Extract designation and session using the appropriate parser
        parser = _REFERENCE_PARSERS.get(doc_type, _parse_nja_reference)
        designation, session = parser(referat_list)

        # Fallback: use case number and year from decision date
        if not designation:
            if mal_list:
                # Remove spaces from case numbers like "T 4847-24"
                designation = mal_list[0].replace(" ", "")
            else:
                designation = pub.get("id", "unknown")

        if not session and avgorandedatum:
            # Extract year from date string "YYYY-MM-DD"
            session = avgorandedatum[:4] if len(avgorandedatum) >= 4 else None

        # Parse decision date
        try:
            doc_date = date.fromisoformat(avgorandedatum) if avgorandedatum else date.today()
        except ValueError:
            logger.warning("Could not parse date '%s', using today", avgorandedatum)
            doc_date = date.today()

        title = pub.get("benamning", "").strip()
        if not title:
            # Build a descriptive title from court name, reference, and case number
            court_name = pub.get("domstol", {}).get("domstolNamn", "")
            ref_str = ", ".join(referat_list) if referat_list else ""
            mal_str = ", ".join(mal_list) if mal_list else ""
            if ref_str:
                title = ref_str
            elif court_name and mal_str:
                title = f"{court_name} mål {mal_str}"
            elif mal_str:
                title = f"Mål {mal_str}"
            else:
                title = designation

        # Build attachments from bilagaLista
        attachments: list[Attachment] = []
        for bilaga in pub.get("bilagaLista", []):
            lagring_id = bilaga.get("fillagringId", "")
            filnamn = bilaga.get("filnamn", "attachment.pdf")
            if lagring_id:
                # lagringId contains slashes (e.g. "190/d3/38/uuid")
                # that must be URL-encoded in the path
                encoded_id = quote(lagring_id, safe="")
                attachments.append(
                    Attachment(
                        filename=filnamn,
                        url=f"{BASE_URL}/api/v1/bilagor/{encoded_id}",
                        mime_type="application/pdf",
                    )
                )

        doc_id = build_doc_id(doc_type, designation, session)

        domstol = pub.get("domstol", {})
        source_id = pub.get("id", "")

        # The API's "innehall" field may contain raw HTML — clean it
        raw_content = pub.get("innehall")
        text: str | None = None
        html: str | None = None
        if raw_content:
            if "<" in raw_content and ">" in raw_content:
                html = raw_content
                text = html_to_text(raw_content)
            else:
                text = raw_content

        return Document(
            doc_id=doc_id,
            doc_type=doc_type,
            designation=designation,
            session=session,
            title=title,
            summary=pub.get("sammanfattning"),
            text=text,
            html=html,
            date=doc_date,
            department=domstol.get("domstolNamn"),
            source=Source.DOMSTOL,
            source_id=source_id,
            source_url=f"{BASE_URL}/api/v1/publiceringar/{source_id}" if source_id else None,
            fetched_at=datetime.now(tz=UTC),
            attachments=attachments,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

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
        """Yield court decisions from the Domstolsverket API."""
        if doc_type not in self.supported_doc_types:
            raise ValueError(f"Unsupported doc type for Domstol: {doc_type}")

        # If session is a year like "2025", convert to date range
        if session and not since and not until:
            try:
                year = int(session)
                since = date(year, 1, 1)
                until = date(year, 12, 31)
            except ValueError:
                pass

        count = 0
        page = 0

        while True:
            params: dict[str, str | int] = {
                "domstolkod": _COURT_MAP[doc_type],
                "page": page,
                "pagesize": PAGE_SIZE,
            }

            logger.debug("Fetching publications page %d", page)
            data = await self._fetch_json("/api/v1/publiceringar", params=params)

            if not data or not isinstance(data, list):
                break

            for pub in data:
                if limit and count >= limit:
                    return

                doc = self._parse_publication(pub, doc_type)
                if not doc:
                    continue

                # Filter by date range
                if since and doc.date < since:
                    continue
                if until and doc.date > until:
                    continue

                # Filter by session if specified and not already converted to dates
                if session and doc.session != session:
                    continue

                yield doc
                count += 1

            # Stop if fewer results than a full page
            if len(data) < PAGE_SIZE:
                break

            page += 1

    async def download_attachments(self, doc: Document, base_dir: Path) -> Document:
        """Download attachments and strip court letterhead from extracted PDF text."""
        doc = await super().download_attachments(doc, base_dir)
        if doc.text:
            doc.text = _strip_court_header(doc.text)
        return doc

    async def get_document(
        self,
        source_id: str,
        doc_type: DocType | None = None,
    ) -> Document | None:
        """Fetch a single publication by its UUID."""
        data = await self._fetch_json(f"/api/v1/publiceringar/{source_id}")
        if not data or not isinstance(data, dict):
            return None
        if doc_type is None:
            court_code = data.get("domstol", {}).get("domstolKod", "HDO")
            reverse_map = {v: k for k, v in _COURT_MAP.items()}
            doc_type = reverse_map.get(court_code, DocType.NJA)
        return self._parse_publication(data, doc_type)
