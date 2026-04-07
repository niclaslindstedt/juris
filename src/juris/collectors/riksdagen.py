"""Riksdagen API collector (data.riksdagen.se)."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any

import httpx

from juris.collectors.base import BaseCollector
from juris.models import Attachment, DocType, Document, Source
from juris.utils import build_doc_id, html_to_text

logger = logging.getLogger(__name__)

BASE_URL = "https://data.riksdagen.se"

# Swedish Riksdag standing committees — maps prefix to full Swedish name
_COMMITTEE_MAP: dict[str, str] = {
    "AU": "Arbetsmarknadsutskottet",
    "CU": "Civilutskottet",
    "FiU": "Finansutskottet",
    "FöU": "Försvarsutskottet",
    "JuU": "Justitieutskottet",
    "KU": "Konstitutionsutskottet",
    "KrU": "Kulturutskottet",
    "MJU": "Miljö- och jordbruksutskottet",
    "NU": "Näringsutskottet",
    "SfU": "Socialförsäkringsutskottet",
    "SkU": "Skatteutskottet",
    "SoU": "Socialutskottet",
    "TU": "Trafikutskottet",
    "UbU": "Utbildningsutskottet",
    "UU": "Utrikesutskottet",
}


def _extract_committee(designation: str) -> str | None:
    """Extract committee name from a BET designation like 'JuU15'."""
    m = re.match(r"^([A-ZÅÄÖ][a-zåäö]*[A-Z][a-zåäö]?)", designation)
    if m:
        return _COMMITTEE_MAP.get(m.group(1))
    return None


# Map our DocType to Riksdagen's doktyp parameter
_DOCTYPE_MAP: dict[DocType, str] = {
    DocType.PROP: "prop",
    DocType.SOU: "sou",
    DocType.MOT: "mot",
    DocType.BET: "bet",
    DocType.DIR: "dir",
    DocType.SKR: "skr",
    DocType.SFS: "sfs",
}

# Doc types where the API requires a subtyp filter.
# SKR documents are now stored under doktyp=prop with subtyp=skr;
# adding subtyp=prop for PROP prevents SKR items leaking into PROP results.
_SUBTYPE_MAP: dict[DocType, str] = {
    DocType.SKR: "skr",
    DocType.PROP: "prop",
}


class RiksdagenCollector(BaseCollector):
    """Collects documents from the Riksdagen open data API."""

    source = Source.RIKSDAGEN
    supported_doc_types = list(_DOCTYPE_MAP.keys())
    preferred_for = [DocType.PROP, DocType.SOU, DocType.DIR, DocType.SKR]

    def __init__(self, rate_limit: float = 0.5) -> None:
        super().__init__(rate_limit=rate_limit, base_url=BASE_URL)

    async def _fetch_json(self, url: str) -> dict[str, Any] | None:
        """Fetch a URL and return parsed JSON, or None on error."""
        await self._limiter.wait()
        client = await self._get_client()
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return None

    async def _fetch_document_html(self, dok_id: str) -> str | None:
        """Fetch the full HTML content for a document."""
        data = await self._fetch_json(f"{BASE_URL}/dokument/{dok_id}.json")
        if not data:
            return None
        doc_data = data.get("dokumentstatus", {}).get("dokument", {})
        html: str | None = doc_data.get("html")
        return html

    def _parse_document(
        self,
        item: dict[str, Any],
        full_html: str | None = None,
        *,
        expected_doc_type: DocType | None = None,
    ) -> Document:
        """Convert a Riksdagen API document item to our Document model."""
        dok_id = item["dok_id"]

        if expected_doc_type is not None:
            doc_type = expected_doc_type
        else:
            # Reverse lookup DocType from Riksdagen's type string
            doc_type_str = item.get("doktyp", "").lower()
            doc_type = DocType.PROP  # default
            for dt, rk_type in _DOCTYPE_MAP.items():
                if rk_type == doc_type_str:
                    doc_type = dt
                    break

        designation = item.get("beteckning", item.get("nummer", ""))
        session = item.get("rm") or None

        # SFS beteckning is "YYYY:NNN" — split into year (session) and number
        if doc_type == DocType.SFS:
            m = re.match(r"^(\d{4}):(.+)$", designation)
            if m:
                session = m.group(1)
                designation = m.group(2)

        doc_id = build_doc_id(doc_type, designation, session)

        # Parse date — format is "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"
        date_str = item.get("datum", "")
        doc_date = date.fromisoformat(date_str[:10]) if date_str else date.today()

        # Text extraction
        text = None
        html = full_html
        if html:
            text = html_to_text(html)

        # Attachments
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

        # Build a summary from undertitel or first substantial text paragraph
        summary = item.get("undertitel") or None
        if not summary and text:
            for paragraph in re.split(r"\n{2,}", text):
                stripped = paragraph.strip()
                # Skip short lines (headings, metadata) and the title itself
                if len(stripped) > 60 and stripped != item.get("titel", ""):
                    summary = stripped[:500]
                    break

        # Extract committee name for committee reports (betänkanden)
        committee = _extract_committee(designation) if doc_type == DocType.BET else None

        return Document(
            doc_id=doc_id,
            doc_type=doc_type,
            designation=designation,
            session=session,
            title=item.get("titel", ""),
            summary=summary,
            text=text,
            html=html,
            date=doc_date,
            department=item.get("organ") or None,
            committee=committee,
            source=Source.RIKSDAGEN,
            source_id=dok_id,
            source_url=f"{BASE_URL}/dokument/{dok_id}",
            fetched_at=datetime.now(tz=UTC),
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
        skip_content: bool = False,
    ) -> AsyncIterator[Document]:
        """Yield documents from the Riksdagen API."""
        if doc_type not in _DOCTYPE_MAP:
            raise ValueError(f"Unsupported doc type for Riksdagen: {doc_type}")

        rk_type = _DOCTYPE_MAP[doc_type]
        # SKR is now filed under doktyp=prop&subtyp=skr in the Riksdagen API
        if doc_type == DocType.SKR:
            rk_type = "prop"
        page_size = 20
        count = 0

        # Build initial URL
        params: dict[str, str] = {
            "doktyp": rk_type,
            "utformat": "json",
            "antal": str(page_size),
            "sida": "1",
            "sort": "datum",
            "sortorder": "desc",
        }
        if doc_type in _SUBTYPE_MAP:
            params["subtyp"] = _SUBTYPE_MAP[doc_type]
        if session:
            if doc_type == DocType.SFS:
                # SFS uses year, not riksmöte — map to date range
                params["from"] = f"{session}-01-01"
                params["tom"] = f"{session}-12-31"
            else:
                params["rm"] = session
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

            # Handle single document (API returns dict instead of list)
            if isinstance(documents, dict):
                documents = [documents]

            for item in documents:
                if limit and count >= limit:
                    return

                dok_id = item.get("dok_id", "")
                logger.info("Fetching %s: %s", dok_id, item.get("titel", "")[:60])

                # Fetch full HTML content (skip when only metadata is wanted)
                html = None if skip_content else await self._fetch_document_html(dok_id)
                doc = self._parse_document(
                    item, full_html=html, expected_doc_type=doc_type
                )
                yield doc
                count += 1

            # Follow pagination
            next_url = doc_list.get("@nasta_sida")
            if next_url and (not limit or count < limit):
                url = next_url
            else:
                break

    async def get_document(self, source_id: str) -> Document | None:
        """Fetch a single document by its Riksdagen dok_id."""
        data = await self._fetch_json(f"{BASE_URL}/dokumentstatus/{source_id}.json")
        if not data:
            return None

        doc_data = data.get("dokumentstatus", {}).get("dokument", {})
        if not doc_data:
            return None

        html = doc_data.get("html")
        return self._parse_document(doc_data, full_html=html)
