"""Collector for myndighetsföreskrifter (regulatory agency rules).

Scrapes föreskrifter from individual Swedish agency websites. Each agency
publishes its own författningssamling (e.g. AFS, SOSFS/HSLF-FS, FFFS).
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from juris.collectors.base import BaseCollector
from juris.models import Attachment, DocType, Document, Source
from juris.utils import build_doc_id, extract_page_content, parse_swedish_date

logger = logging.getLogger(__name__)

# Regex for föreskrift designations: "AFS 2023:1", "HSLF-FS 2026:3", etc.
_FORESKRIFT_RE = re.compile(r"([A-ZÅÄÖ][\w-]*FS)\s+(\d{4}):(\d+)")


@dataclass
class _AgencyConfig:
    """Configuration for scraping a specific agency's författningssamling."""

    prefix: str  # e.g. "AFS"
    agency_name: str  # e.g. "Arbetsmiljöverket"
    base_url: str
    listing_url: str
    paginated: bool = False
    page_param: str = "p"
    page_size: int = 20


# Supported agencies — extend this list to add more.
_AGENCIES: dict[str, _AgencyConfig] = {
    "AFS": _AgencyConfig(
        prefix="AFS",
        agency_name="Arbetsmiljöverket",
        base_url="https://www.av.se",
        listing_url="https://www.av.se/arbetsmiljoarbete-och-inspektioner/publikationer/foreskrifter/",
        paginated=False,
    ),
    "SOSFS": _AgencyConfig(
        prefix="SOSFS",
        agency_name="Socialstyrelsen",
        base_url="https://www.socialstyrelsen.se",
        listing_url="https://www.socialstyrelsen.se/kunskapsstod-och-regler/regler-och-riktlinjer/foreskrifter-och-allmanna-rad/",
        paginated=True,
        page_param="page",
        page_size=20,
    ),
    "HSLF-FS": _AgencyConfig(
        prefix="HSLF-FS",
        agency_name="Socialstyrelsen",
        base_url="https://www.socialstyrelsen.se",
        listing_url="https://www.socialstyrelsen.se/kunskapsstod-och-regler/regler-och-riktlinjer/foreskrifter-och-allmanna-rad/",
        paginated=True,
        page_param="page",
        page_size=20,
    ),
}


def _parse_iso_date(text: str) -> date | None:
    """Parse an ISO date string like '2023-09-15'."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


class LagrummetCollector(BaseCollector):
    """Collects myndighetsföreskrifter from Swedish agency websites."""

    source = Source.LAGRUMMET
    supported_doc_types = [DocType.FORESKRIFT]

    def __init__(self, rate_limit: float = 1.0) -> None:
        super().__init__(rate_limit=rate_limit, follow_redirects=True)

    async def _fetch_html(self, url: str) -> str | None:
        """Fetch a URL and return HTML text, or None on error."""
        await self._limiter.wait()
        client = await self._get_client()
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return None

    # ------------------------------------------------------------------
    # Listing page parsing
    # ------------------------------------------------------------------

    def _parse_listing_page(self, html: str, agency: _AgencyConfig) -> list[dict[str, str]]:
        """Parse a listing page and return items with url, title, designation."""
        soup = BeautifulSoup(html, "lxml")
        items: list[dict[str, str]] = []

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not isinstance(href, str):
                continue
            text = link.get_text(strip=True)
            if not text:
                continue

            # Look for designation patterns in the link text
            m = _FORESKRIFT_RE.search(text)
            if not m:
                continue

            prefix = m.group(1)
            # Only include entries matching the target agency prefix
            if prefix != agency.prefix:
                continue

            full_url = urljoin(agency.base_url, href)
            items.append(
                {
                    "url": full_url,
                    "title": text,
                    "prefix": prefix,
                    "year": m.group(2),
                    "number": m.group(3),
                }
            )

        return items

    # ------------------------------------------------------------------
    # Detail page parsing
    # ------------------------------------------------------------------

    def _parse_detail_page(
        self, html: str, page_url: str, agency: _AgencyConfig
    ) -> Document | None:
        """Parse a document detail page into a Document model."""
        soup = BeautifulSoup(html, "lxml")

        # Title: first <h1>, but skip cookie banners
        title = ""
        for h in soup.find_all(["h1", "h2"]):
            candidate = h.get_text(strip=True)
            if candidate and not re.search(r"kakor|cookies|cookie", candidate, re.I):
                title = candidate
                break
        if not title:
            logger.warning("No title found on %s", page_url)
            return None

        page_text = soup.get_text(" ", strip=True)

        # Designation from page text
        m = _FORESKRIFT_RE.search(page_text)
        if m:
            prefix, year, number = m.group(1), m.group(2), m.group(3)
            designation = f"{prefix} {year}:{number}"
            session = year
        else:
            # Fallback: try URL
            m_url = _FORESKRIFT_RE.search(page_url)
            if m_url:
                prefix, year, number = m_url.group(1), m_url.group(2), m_url.group(3)
                designation = f"{prefix} {year}:{number}"
                session = year
            else:
                logger.warning("Could not parse designation from %s", page_url)
                slug = page_url.rstrip("/").rsplit("/", 1)[-1]
                designation = slug
                session = None

        # Date: try ISO format first, then Swedish
        doc_date: date | None = None
        # Look for patterns like "Beslutsdatum: 2023-09-15" or "Publicerad: 2023-09-15"
        date_match = re.search(
            r"(?:Beslutsdatum|Publicerad|Beslutad|Utfärdad)[:\s]+(\d{4}-\d{2}-\d{2})",
            page_text,
        )
        if date_match:
            doc_date = _parse_iso_date(date_match.group(1))
        if not doc_date:
            date_match = re.search(
                r"(?:Beslutsdatum|Publicerad|Beslutad|Utfärdad)[:\s]+(\d{1,2}\s+\w+\s+\d{4})",
                page_text,
            )
            if date_match:
                doc_date = parse_swedish_date(date_match.group(1))
        if not doc_date:
            # Try any ISO date on the page
            doc_date = _parse_iso_date(page_text)
        if not doc_date:
            logger.warning("Could not parse date from %s, using today", page_url)
            doc_date = date.today()

        # Extract main content
        summary_text, summary_html = extract_page_content(soup)

        # Build a clean summary from the first substantial paragraph
        clean_summary: str | None = None
        if summary_text:
            for paragraph in re.split(r"\n{2,}", summary_text):
                stripped = paragraph.strip()
                if len(stripped) > 60:
                    clean_summary = stripped[:500]
                    break

        # PDF attachments
        attachments: list[Attachment] = []
        for pdf_link in soup.find_all("a", href=re.compile(r"\.pdf", re.IGNORECASE)):
            href = pdf_link["href"]
            if not isinstance(href, str):
                continue
            pdf_url = urljoin(page_url, href)
            filename = pdf_url.rsplit("/", 1)[-1].split("?")[0]
            attachments.append(
                Attachment(
                    filename=filename,
                    url=pdf_url,
                    mime_type="application/pdf",
                )
            )

        source_id = page_url.replace(agency.base_url, "")
        doc_id = build_doc_id(DocType.FORESKRIFT, designation, session)

        return Document(
            doc_id=doc_id,
            doc_type=DocType.FORESKRIFT,
            designation=designation,
            session=session,
            title=title,
            summary=clean_summary,
            text=summary_text,
            html=summary_html,
            date=doc_date,
            department=agency.agency_name,
            source=Source.LAGRUMMET,
            source_id=source_id,
            source_url=page_url,
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
        """Yield föreskrifter from configured agency websites."""
        if doc_type != DocType.FORESKRIFT:
            raise ValueError(f"Unsupported doc type for Lagrummet: {doc_type}")

        count = 0

        for agency in _AGENCIES.values():
            if limit and count >= limit:
                return

            logger.info("Collecting %s from %s", agency.prefix, agency.agency_name)
            page = 1

            while True:
                # Build listing URL
                listing_url = agency.listing_url
                if agency.paginated and page > 1:
                    sep = "&" if "?" in listing_url else "?"
                    listing_url = f"{listing_url}{sep}{agency.page_param}={page}"

                logger.info("Fetching listing page %d: %s", page, listing_url)
                html = await self._fetch_html(listing_url)
                if not html:
                    break

                items = self._parse_listing_page(html, agency)
                if not items:
                    logger.info("No items found on page %d, stopping.", page)
                    break

                for item in items:
                    if limit and count >= limit:
                        return

                    # Filter by session (year) if requested
                    if session and item["year"] != session:
                        continue

                    if skip_content:
                        # Build a lightweight Document from listing data alone,
                        # avoiding the detail page fetch entirely.
                        designation = f"{item['prefix']} {item['year']}:{item['number']}"
                        year = int(item["year"])
                        approx_date = date(year, 1, 1)
                        if since and approx_date < since:
                            continue
                        if until and approx_date > until:
                            continue
                        doc = Document(
                            doc_id=build_doc_id(DocType.FORESKRIFT, designation, item["year"]),
                            doc_type=DocType.FORESKRIFT,
                            designation=designation,
                            session=item["year"],
                            title=item["title"],
                            date=approx_date,
                            department=agency.agency_name,
                            source=Source.LAGRUMMET,
                            source_url=item["url"],
                            fetched_at=datetime.now(tz=UTC),
                        )
                        yield doc
                        count += 1
                        continue

                    logger.info("Fetching detail: %s", item["title"][:80])
                    detail_html = await self._fetch_html(item["url"])
                    if not detail_html:
                        continue

                    detail_doc = self._parse_detail_page(detail_html, item["url"], agency)
                    if not detail_doc:
                        continue

                    # Filter by date range
                    if since and detail_doc.date < since:
                        continue
                    if until and detail_doc.date > until:
                        continue

                    yield detail_doc
                    count += 1

                # Stop pagination for non-paginated agencies or end of results
                if not agency.paginated:
                    break
                if len(items) < agency.page_size:
                    break

                page += 1

    async def get_document(self, source_id: str) -> Document | None:
        """Fetch a single document by its source-relative URL path."""
        # Determine which agency the source_id belongs to
        for agency in _AGENCIES.values():
            if source_id.startswith("/"):
                url = agency.base_url + source_id
                html = await self._fetch_html(url)
                if html:
                    return self._parse_detail_page(html, url, agency)
        return None
