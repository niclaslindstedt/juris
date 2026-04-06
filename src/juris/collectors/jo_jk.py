"""JO/JK decisions collector (www.jo.se / www.jk.se).

JO (Justitieombudsmannen) — Parliamentary Ombudsman decisions.
JK (Justitiekanslern) — Chancellor of Justice decisions.

JO uses sitemap-based discovery (WordPress site with decision pages at /besluten/).
JK uses listing-page scraping at /beslut/ with pagination.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from urllib.parse import urlencode, urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from juris.collectors.base import BaseCollector
from juris.models import Attachment, DocType, Document, Source
from juris.utils import build_doc_id, extract_page_content

logger = logging.getLogger(__name__)

JO_BASE_URL = "https://www.jo.se"
JK_BASE_URL = "https://www.jk.se"

# Number of sitemap files to try for JO (resolve-sitemap1.xml .. resolve-sitemap20.xml)
_JO_SITEMAP_COUNT = 20

# JK listing page size (for pagination stop condition)
_JK_PAGE_SIZE = 20

# Regex patterns for metadata extraction from detail pages
_DNR_RE = re.compile(r"Diarienummer[:\s]+(\d{1,5}[–\-]\d{2,4})")
_DATE_RE = re.compile(r"Beslutsdatum[:\s]+(\d{4}-\d{2}-\d{2})")
_DECISION_MAKER_RE = re.compile(
    r"Beslutsfattare[:\s]+(.+?)(?=\s+Ladda|\s+Beslutsdatum|\s+Diarienummer|$)"
)

# XML namespace used in sitemaps
_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class JoJkCollector(BaseCollector):
    """Scrapes decisions from JO (jo.se) and JK (jk.se)."""

    source = Source.JO_JK
    supported_doc_types = [DocType.JO, DocType.JK]

    def __init__(self, rate_limit: float = 1.0) -> None:
        super().__init__(rate_limit=rate_limit, follow_redirects=True)

    async def _fetch_html(self, url: str) -> str | None:
        """Fetch a URL and return the response text, or None on error."""
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
    # JO: Sitemap-based URL discovery
    # ------------------------------------------------------------------

    async def _fetch_jo_sitemap_urls(
        self,
        since: date | None = None,
        until: date | None = None,
    ) -> list[dict[str, str]]:
        """Parse JO resolve-sitemap XML files to collect decision URLs.

        Returns list of dicts with keys: url, lastmod.
        Only includes URLs under /besluten/ and applies date filtering
        based on the <lastmod> field in the sitemap.
        """
        results: list[dict[str, str]] = []

        for i in range(1, _JO_SITEMAP_COUNT + 1):
            sitemap_url = f"{JO_BASE_URL}/resolve-sitemap{i}.xml"
            xml_text = await self._fetch_html(sitemap_url)
            if not xml_text:
                continue

            try:
                root = ET.fromstring(xml_text)
            except ET.ParseError as e:
                logger.warning("Failed to parse sitemap %s: %s", sitemap_url, e)
                continue

            for url_el in root.findall("sm:url", _SITEMAP_NS):
                loc_el = url_el.find("sm:loc", _SITEMAP_NS)
                if loc_el is None or loc_el.text is None:
                    continue

                loc = loc_el.text.strip()
                # Must be a decision detail page (not the /besluten/ landing page)
                if not re.search(r"/besluten/.+", loc):
                    continue

                lastmod = ""
                lastmod_el = url_el.find("sm:lastmod", _SITEMAP_NS)
                if lastmod_el is not None and lastmod_el.text:
                    lastmod = lastmod_el.text.strip()

                # Filter by date if possible
                if lastmod and (since or until):
                    try:
                        mod_date = date.fromisoformat(lastmod[:10])
                        if since and mod_date < since:
                            continue
                        if until and mod_date > until:
                            continue
                    except ValueError:
                        pass

                results.append({"url": loc, "lastmod": lastmod})

        logger.info("Found %d JO decision URLs from sitemaps", len(results))
        return results

    # ------------------------------------------------------------------
    # JK: Listing-page-based URL discovery
    # ------------------------------------------------------------------

    async def _fetch_jk_listing_urls(
        self,
        since: date | None = None,
        until: date | None = None,
    ) -> list[dict[str, str]]:
        """Scrape JK listing pages to collect decision URLs.

        Returns list of dicts with keys: url, title.
        """
        results: list[dict[str, str]] = []
        page = 1

        while True:
            params: dict[str, str] = {"page": str(page)}
            if since:
                params["from"] = since.isoformat()
            if until:
                params["to"] = until.isoformat()

            listing_url = f"{JK_BASE_URL}/beslut/?{urlencode(params)}"
            html = await self._fetch_html(listing_url)
            if not html:
                break

            soup = BeautifulSoup(html, "lxml")
            items: list[dict[str, str]] = []

            # Strategy 1: <article> elements with links
            for article in soup.find_all("article"):
                link = article.find("a", href=True)
                if link and isinstance(link, Tag):
                    href = str(link["href"])
                    title = link.get_text(strip=True)
                    if title and ("/beslut/" in href or "/besluten/" in href):
                        items.append({
                            "url": urljoin(JK_BASE_URL, href),
                            "title": title,
                        })

            # Strategy 2: scan all links matching decision patterns
            if not items:
                for link in soup.find_all("a", href=True):
                    href = str(link["href"])
                    title = link.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue
                    if re.search(r"/beslut/\d{4}/", href) or "/arenden/" in href:
                        items.append({
                            "url": urljoin(JK_BASE_URL, href),
                            "title": title,
                        })

            if not items:
                break

            results.extend(items)

            if len(items) < _JK_PAGE_SIZE:
                break
            page += 1

        logger.info("Found %d JK decision URLs from listing pages", len(results))
        return results

    # ------------------------------------------------------------------
    # Detail page parsing (shared between JO and JK)
    # ------------------------------------------------------------------

    def _parse_detail_page(
        self, html: str, page_url: str, doc_type: DocType
    ) -> Document | None:
        """Parse a decision detail page into a Document model."""
        base_url = JO_BASE_URL if doc_type == DocType.JO else JK_BASE_URL
        soup = BeautifulSoup(html, "lxml")

        # Title from <h1>
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else ""
        if not title:
            logger.warning("No title found on %s", page_url)
            return None

        page_text = soup.get_text(" ", strip=True)

        # Beslutsdatum (decision date)
        doc_date: date | None = None
        date_match = _DATE_RE.search(page_text)
        if date_match:
            try:
                doc_date = date.fromisoformat(date_match.group(1))
            except ValueError:
                pass
        if not doc_date:
            # Fallback: try ISO date anywhere in text
            iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", page_text)
            if iso_match:
                try:
                    doc_date = date.fromisoformat(iso_match.group(1))
                except ValueError:
                    pass
        if not doc_date:
            logger.warning("Could not parse date from %s, using today", page_url)
            doc_date = date.today()

        # Diarienummer (case reference number) as designation
        designation = ""
        session: str | None = None
        dnr_match = _DNR_RE.search(page_text)
        if dnr_match:
            designation = dnr_match.group(1).replace("\u2013", "-")  # normalize en-dash
            # Extract year from dnr (e.g. "6037-2025" -> "2025")
            year_match = re.search(r"-(\d{4})$", designation)
            if year_match:
                session = year_match.group(1)
            else:
                year_match = re.search(r"-(\d{2})$", designation)
                if year_match:
                    session = f"20{year_match.group(1)}"

        if not designation:
            # Fallback: use URL slug
            slug = page_url.rstrip("/").rsplit("/", 1)[-1]
            designation = slug

        if not session:
            session = str(doc_date.year)

        # Beslutsfattare (decision maker) -> department
        department: str | None = None
        maker_match = _DECISION_MAKER_RE.search(page_text)
        if maker_match:
            department = maker_match.group(1).strip()

        # PDF attachments (extract before content, as content extraction mutates soup)
        attachments = self._extract_attachments(soup, base_url)

        # Extract main content
        summary_text, summary_html = extract_page_content(soup)

        # Build a clean summary from the first substantial paragraph,
        # skipping tag-like fragments (category labels, short metadata)
        clean_summary: str | None = None
        if summary_text:
            for paragraph in re.split(r"\n{2,}", summary_text):
                stripped = paragraph.strip()
                if len(stripped) > 60:
                    clean_summary = stripped[:500]
                    break

        source_id = page_url.replace(base_url, "")
        doc_id = build_doc_id(doc_type, designation, session)

        return Document(
            doc_id=doc_id,
            doc_type=doc_type,
            designation=designation,
            session=session,
            title=title,
            summary=clean_summary,
            text=summary_text,
            html=summary_html,
            date=doc_date,
            department=department,
            source=Source.JO_JK,
            source_id=source_id,
            source_url=page_url,
            fetched_at=datetime.now(tz=UTC),
            attachments=attachments,
        )

    @staticmethod
    def _extract_attachments(soup: BeautifulSoup, base_url: str) -> list[Attachment]:
        """Find PDF links on the page."""
        attachments: list[Attachment] = []
        seen_urls: set[str] = set()
        for pdf_link in soup.find_all("a", href=re.compile(r"\.pdf$", re.IGNORECASE)):
            href = pdf_link["href"]
            if not isinstance(href, str):
                continue
            pdf_url = urljoin(base_url, href)
            # Skip external URLs (e.g. docreader services)
            if not pdf_url.startswith(base_url):
                continue
            if pdf_url in seen_urls:
                continue
            seen_urls.add(pdf_url)
            filename = pdf_url.rsplit("/", 1)[-1]
            attachments.append(
                Attachment(
                    filename=filename,
                    url=pdf_url,
                    mime_type="application/pdf",
                )
            )
        return attachments

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
        """Yield decisions from JO or JK."""
        if doc_type not in self.supported_doc_types:
            raise ValueError(f"Unsupported doc type for JO/JK: {doc_type}")

        # Discover decision URLs
        if doc_type == DocType.JO:
            urls = await self._fetch_jo_sitemap_urls(since=since, until=until)
            items = [{"url": u["url"]} for u in urls]
        else:
            items = await self._fetch_jk_listing_urls(since=since, until=until)

        count = 0
        for item in items:
            if limit is not None and count >= limit:
                return

            detail_html = await self._fetch_html(item["url"])
            if not detail_html:
                continue

            doc = self._parse_detail_page(detail_html, item["url"], doc_type)
            if not doc:
                continue

            # Filter by session/year if requested
            if session and doc.session != session:
                continue

            # Extra date filtering for detail-page dates (sitemap lastmod
            # is only an approximation)
            if since and doc.date < since:
                continue
            if until and doc.date > until:
                continue

            yield doc
            count += 1

    async def get_document(self, source_id: str) -> Document | None:
        """Fetch a single decision by its relative URL path."""
        # Determine doc_type from the URL
        if source_id.startswith("/besluten/"):
            base_url = JO_BASE_URL
            doc_type = DocType.JO
        else:
            base_url = JK_BASE_URL
            doc_type = DocType.JK

        url = base_url + source_id
        html = await self._fetch_html(url)
        if not html:
            return None

        return self._parse_detail_page(html, url, doc_type)
