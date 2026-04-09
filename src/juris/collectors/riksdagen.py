"""Riksdagen API collector (data.riksdagen.se)."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

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
        self._last_fetch_error: str | None = None

    async def _fetch_json(self, url: str) -> dict[str, Any] | None:
        """Fetch a URL and return parsed JSON, or None on error."""
        try:
            resp = await self._fetch_with_retry("GET", url)
            result: dict[str, Any] = resp.json()
            return result
        except httpx.HTTPStatusError as e:
            self._last_fetch_error = f"HTTP {e.response.status_code}"
            logger.warning("Failed to fetch %s: HTTP %d", url, e.response.status_code)
            return None
        except httpx.HTTPError as e:
            self._last_fetch_error = type(e).__name__
            logger.warning("Failed to fetch %s: %s", url, type(e).__name__)
            return None
        except ValueError as e:
            self._last_fetch_error = f"JSON parse error: {e}"
            logger.warning("Failed to parse JSON from %s: %s", url, e)
            return None

    async def _fetch_document_html(self, dok_id: str) -> str | None:
        """Fetch the full HTML content for a document."""
        data = await self._fetch_json(f"{BASE_URL}/dokument/{dok_id}.json")
        if not data:
            return None
        doc_data = data.get("dokumentstatus", {}).get("dokument", {})
        html: str | None = doc_data.get("html")
        return html

    @staticmethod
    def _url_with_page(url: str, page: int) -> str | None:
        """Return a copy of *url* with the ``p`` query parameter set to *page*."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "p" not in params:
            return None
        params["p"] = [str(page)]
        return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

    async def _verify_pagination_end(
        self, failed_url: str, prev_url: str | None, count: int
    ) -> None:
        """Check adjacent pages to determine if a fetch failure is the natural end.

        After a page fetch fails during pagination, this method re-fetches the
        previous page (to confirm connectivity) and tries the next page (to
        confirm it also fails).  The results are logged so the user can see
        whether this is the normal end of results or a possible ban/rate-limit.
        """
        parsed = urlparse(failed_url)
        params = parse_qs(parsed.query)
        page_strs = params.get("p")
        if not page_strs:
            # No pagination parameter — can't verify
            return
        current_page = int(page_strs[0])

        logger.info("Verifying end of results (failed at page %d)…", current_page)

        # Check previous page
        check_prev = prev_url or self._url_with_page(failed_url, current_page - 1)
        prev_ok = False
        if check_prev and current_page > 1:
            prev_data = await self._fetch_json(check_prev)
            prev_ok = bool(prev_data and prev_data.get("dokumentlista", {}).get("dokument"))

        # Check next page
        next_url = self._url_with_page(failed_url, current_page + 1)
        next_ok = False
        if next_url:
            next_data = await self._fetch_json(next_url)
            next_ok = bool(next_data and next_data.get("dokumentlista", {}).get("dokument"))

        if prev_ok and not next_ok:
            logger.info(
                "Confirmed end of results at page %d (%d documents). "
                "Previous page OK, next page also has no results.",
                current_page,
                count,
            )
        elif not prev_ok:
            logger.warning(
                "Possible rate limit or block: previous page (page %d) also failed. "
                "Results may be incomplete (%d documents collected from %d pages).",
                current_page - 1,
                count,
                current_page - 1,
            )
        else:
            # prev_ok and next_ok — the failed page is an isolated gap
            logger.warning(
                "Unexpected gap at page %d (previous and next pages both OK). "
                "%d documents collected — results may have gaps.",
                current_page,
                count,
            )

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
        offset: int = 0,
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
        items_to_skip = offset % page_size

        # Build initial URL
        start_sida = offset // page_size + 1
        params: dict[str, str] = {
            "doktyp": rk_type,
            "utformat": "json",
            "antal": str(page_size),
            "sida": str(start_sida),
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
        prev_url: str | None = None

        while url:
            data = await self._fetch_json(url)
            if not data:
                if count > 0:
                    await self._verify_pagination_end(url, prev_url, count)
                else:
                    logger.warning(
                        "Failed to fetch initial page: %s",
                        self._last_fetch_error or "unknown error",
                    )
                break

            doc_list = data.get("dokumentlista", {})

            # Capture API-reported total on first page
            if self.total_available is None:
                traffar = doc_list.get("@traffar")
                if traffar:
                    try:
                        self.total_available = int(traffar)
                    except (ValueError, TypeError):
                        pass

            documents = doc_list.get("dokument", [])

            if not documents:
                break

            # Handle single document (API returns dict instead of list)
            if isinstance(documents, dict):
                documents = [documents]

            for item in documents:
                if limit and count >= limit:
                    return

                # Skip items on the first page when resuming from offset
                if items_to_skip > 0:
                    items_to_skip -= 1
                    continue

                dok_id = item.get("dok_id", "")
                logger.debug("Fetching %s: %s", dok_id, item.get("titel", "")[:60])

                # Fetch full HTML content (skip when only metadata is wanted)
                html = None if skip_content else await self._fetch_document_html(dok_id)
                doc = self._parse_document(item, full_html=html, expected_doc_type=doc_type)
                yield doc
                count += 1

            # Follow pagination
            next_url = doc_list.get("@nasta_sida")
            if next_url and (not limit or count < limit):
                prev_url = url
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
