"""JO/JK decisions collector (www.jo.se / www.jk.se).

JO (Justitieombudsmannen) — Parliamentary Ombudsman decisions.
JK (Justitiekanslern) — Chancellor of Justice decisions.

JO uses sitemap-based discovery (WordPress site with decision pages at /besluten/).
JK uses POST-based search scraping at /beslut-och-yttranden/ with pagination.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from juris.collectors.base import BaseCollector
from juris.models import Attachment, DocType, Document, SearchResult, Source
from juris.utils import build_doc_id, extract_page_content

logger = logging.getLogger(__name__)

JO_BASE_URL = "https://www.jo.se"
JK_BASE_URL = "https://www.jk.se"

# Number of sitemap files to try for JO (resolve-sitemap1.xml .. resolve-sitemap20.xml)
_JO_SITEMAP_COUNT = 20

# JK search endpoint (new site uses POST-based search)
_JK_SEARCH_URL = f"{JK_BASE_URL}/beslut-och-yttranden/"

# All JK decision category IDs (checkboxes on the search form)
_JK_CATEGORY_IDS = ["39", "40", "41", "42", "43"]

# Regex patterns for metadata extraction from JO detail pages
_DNR_RE = re.compile(r"Diarienummer[:\s]+(\d{1,5}[–\-]\d{2,4})")
_DATE_RE = re.compile(r"Beslutsdatum[:\s]+(\d{4}-\d{2}-\d{2})")
_DECISION_MAKER_RE = re.compile(
    r"Beslutsfattare[:\s]+(.+?)(?=\s+Ladda|\s+Beslutsdatum|\s+Diarienummer|$)"
)

# JK metadata regex: "Diarienr: 2025/7175 / Beslutsdatum: 04 mar 2026"
_JK_DNR_RE = re.compile(r"Diarienr:\s*(\d{4}/\d+)")
_JK_DATE_RE = re.compile(r"Beslutsdatum:\s*(\d{1,2}\s+\w+\s+\d{4})")

# Swedish month name to number mapping
_SV_MONTHS: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}

# XML namespace used in sitemaps
_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# Default start year for JK decisions (site has decisions from 2000 onwards)
_JK_DEFAULT_START = "2000-01-01"


def _parse_swedish_date(text: str) -> date | None:
    """Parse a Swedish date like '04 mar 2026' or '4 mar 2026'."""
    match = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", text.strip())
    if not match:
        return None
    day, month_str, year = match.groups()
    month = _SV_MONTHS.get(month_str.lower())
    if not month:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


class JoJkCollector(BaseCollector):
    """Scrapes decisions from JO (jo.se) and JK (jk.se)."""

    source = Source.JO_JK
    supported_doc_types = [DocType.JO, DocType.JK]
    supports_search = True

    def __init__(self, rate_limit: float = 1.0) -> None:
        super().__init__(rate_limit=rate_limit, follow_redirects=True)

    async def _fetch_html(self, url: str) -> str | None:
        """Fetch a URL via GET and return the response text, or None on error."""
        await self._limiter.wait()
        client = await self._get_client()
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return None

    async def _post_html(
        self, url: str, data: dict[str, str | list[str]]
    ) -> str | None:
        """POST form data to a URL and return the response text, or None on error."""
        await self._limiter.wait()
        client = await self._get_client()
        try:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Failed to POST %s: %s", url, e)
            return None

    # ------------------------------------------------------------------
    # JO: Sitemap-based URL discovery
    # ------------------------------------------------------------------

    async def _fetch_jo_sitemap_urls(
        self,
        since: date | None = None,
        until: date | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        """Parse JO resolve-sitemap XML files to collect decision URLs.

        Returns list of dicts with keys: url, lastmod.
        Only includes URLs under /besluten/ and applies date filtering
        based on the <lastmod> field in the sitemap.
        """
        results: list[dict[str, str]] = []

        for i in range(1, _JO_SITEMAP_COUNT + 1):
            if limit and len(results) >= limit:
                break
            logger.info("JO: fetching sitemap %d/%d...", i, _JO_SITEMAP_COUNT)
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
    # JK: POST-based search discovery
    # ------------------------------------------------------------------

    async def _fetch_jk_listing_urls(
        self,
        since: date | None = None,
        until: date | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        """Scrape JK search results via POST to collect decision URLs.

        Returns list of dicts with keys: url, title.
        """
        results: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        page = 1

        from_date = since.isoformat() if since else _JK_DEFAULT_START
        to_date = until.isoformat() if until else date.today().isoformat()

        while True:
            if limit and len(results) >= limit:
                break
            logger.info("JK: fetching search page %d...", page)
            form_data: dict[str, str | list[str]] = {
                "diarienummer": "",
                "search": "",
                "from-date": from_date,
                "to-date": to_date,
                "typ": list(_JK_CATEGORY_IDS),
                "do-search": "",
                "page": str(page),
            }

            html = await self._post_html(_JK_SEARCH_URL, form_data)
            if not html:
                if page == 1:
                    logger.error(
                        "JK site (%s) is unreachable — skipping JK collection. "
                        "The site may be temporarily down.",
                        JK_BASE_URL,
                    )
                break

            soup = BeautifulSoup(html, "lxml")
            items = self._parse_jk_search_results(soup)

            if not items:
                break

            new_count = 0
            for item in items:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    results.append(item)
                    new_count += 1

            # No new results means we've exhausted all pages
            if new_count == 0:
                break

            page += 1

        logger.info("Found %d JK decision URLs from search", len(results))
        return results

    @staticmethod
    def _parse_jk_search_results(soup: BeautifulSoup) -> list[dict[str, str]]:
        """Parse decision links from the 'Sökresultat' section of a JK search page.

        Returns list of dicts with keys: url, title, and optionally
        designation (diarienummer) and date (ISO format).
        """
        items: list[dict[str, str]] = []

        # Find the search results container (first div.results inside div.ruling-results)
        ruling_results = soup.find("div", class_="ruling-results")
        if not ruling_results or not isinstance(ruling_results, Tag):
            return items

        # The first div.results contains search results; the second is "Senaste beslut"
        results_div = ruling_results.find("div", class_="results")
        if not results_div or not isinstance(results_div, Tag):
            return items

        # Each result is a pair: <div class="date">...</div> <h2><a href="...">title</a></h2>
        for h2 in results_div.find_all("h2"):
            link = h2.find("a", href=True)
            if not link or not isinstance(link, Tag):
                continue
            href = str(link["href"])
            if "/beslut-och-yttranden/" not in href:
                continue
            title = link.get_text(strip=True)
            if not title:
                continue
            item: dict[str, str] = {
                "url": urljoin(JK_BASE_URL, href),
                "title": title,
            }

            # Extract metadata from the preceding div.date sibling
            date_div = h2.find_previous_sibling("div", class_="date")
            if date_div and isinstance(date_div, Tag):
                date_text = date_div.get_text(" ", strip=True)
                dnr_match = _JK_DNR_RE.search(date_text)
                if dnr_match:
                    item["designation"] = dnr_match.group(1)
                jk_date_match = _JK_DATE_RE.search(date_text)
                if jk_date_match:
                    parsed = _parse_swedish_date(jk_date_match.group(1))
                    if parsed:
                        item["date"] = parsed.isoformat()

            items.append(item)

        return items

    # ------------------------------------------------------------------
    # Detail page parsing — JO (legacy shared parser)
    # ------------------------------------------------------------------

    def _parse_jo_detail_page(
        self, html: str, page_url: str
    ) -> Document | None:
        """Parse a JO decision detail page into a Document model."""
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
            designation = dnr_match.group(1).replace("\u2013", "-")
            year_match = re.search(r"-(\d{4})$", designation)
            if year_match:
                session = year_match.group(1)
            else:
                year_match = re.search(r"-(\d{2})$", designation)
                if year_match:
                    session = f"20{year_match.group(1)}"

        if not designation:
            slug = page_url.rstrip("/").rsplit("/", 1)[-1]
            designation = slug

        if not session:
            session = str(doc_date.year)

        # Beslutsfattare (decision maker) -> department
        department: str | None = None
        maker_match = _DECISION_MAKER_RE.search(page_text)
        if maker_match:
            department = maker_match.group(1).strip()

        attachments = self._extract_attachments(soup, JO_BASE_URL)
        summary_text, summary_html = extract_page_content(soup)

        clean_summary: str | None = None
        if summary_text:
            for paragraph in re.split(r"\n{2,}", summary_text):
                stripped = paragraph.strip()
                if len(stripped) > 60:
                    clean_summary = stripped[:500]
                    break

        source_id = page_url.replace(JO_BASE_URL, "")
        doc_id = build_doc_id(DocType.JO, designation, session)

        return Document(
            doc_id=doc_id,
            doc_type=DocType.JO,
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

    # ------------------------------------------------------------------
    # Detail page parsing — JK (new site structure)
    # ------------------------------------------------------------------

    def _parse_jk_detail_page(
        self, html: str, page_url: str
    ) -> Document | None:
        """Parse a JK decision detail page into a Document model.

        The new JK site has this structure inside div.content:
          <div class="date">Diarienr: 2025/7175 <span>/</span> Beslutsdatum: 4 mar 2026</div>
          <h2>Title</h2>
          <p>Decision text...</p>
        """
        soup = BeautifulSoup(html, "lxml")

        # Find the main content div
        content_div = soup.find("div", class_="content")
        if not content_div or not isinstance(content_div, Tag):
            logger.warning("No content div found on %s", page_url)
            return None

        # Parse metadata from div.date
        date_div = content_div.find("div", class_="date")
        date_text = date_div.get_text(" ", strip=True) if date_div else ""

        # Diarienummer: "2025/7175"
        designation = ""
        session: str | None = None
        dnr_match = _JK_DNR_RE.search(date_text)
        if dnr_match:
            designation = dnr_match.group(1)  # e.g. "2025/7175"
            year_match = re.match(r"(\d{4})/", designation)
            if year_match:
                session = year_match.group(1)

        # Beslutsdatum: Swedish format "4 mar 2026"
        doc_date: date | None = None
        jk_date_match = _JK_DATE_RE.search(date_text)
        if jk_date_match:
            doc_date = _parse_swedish_date(jk_date_match.group(1))

        if not doc_date:
            logger.warning("Could not parse date from %s, using today", page_url)
            doc_date = date.today()

        if not designation:
            slug = page_url.rstrip("/").rsplit("/", 1)[-1]
            designation = slug

        if not session:
            session = str(doc_date.year)

        # Title from the first <h2> in content div
        h2 = content_div.find("h2")
        title = h2.get_text(strip=True) if h2 else ""
        if not title:
            logger.warning("No title found on %s", page_url)
            return None

        # PDF attachments
        attachments = self._extract_attachments(soup, JK_BASE_URL)

        # Extract text content: everything in the content div after the date and title.
        # Remove date div and actions div before extracting, clone to avoid mutating soup.
        content_clone = BeautifulSoup(str(content_div), "lxml")
        for el in content_clone.find_all("div", class_=["date", "actions"]):
            el.decompose()

        text_parts: list[str] = []
        html_parts: list[str] = []
        body = content_clone.find("div", class_="content")
        if body and isinstance(body, Tag):
            for child in body.children:
                if isinstance(child, Tag) and child.name in (
                    "p", "h2", "h3", "h4", "ul", "ol", "blockquote"
                ):
                    txt = child.get_text(strip=True)
                    if txt:
                        text_parts.append(txt)
                        html_parts.append(str(child))

        summary_text = "\n\n".join(text_parts) if text_parts else None
        summary_html = "\n".join(html_parts) if html_parts else None

        # Build a clean summary from the first substantial paragraph
        clean_summary: str | None = None
        if summary_text:
            for paragraph in text_parts:
                if len(paragraph) > 60:
                    clean_summary = paragraph[:500]
                    break

        source_id = page_url.replace(JK_BASE_URL, "")
        doc_id = build_doc_id(DocType.JK, designation, session)

        return Document(
            doc_id=doc_id,
            doc_type=DocType.JK,
            designation=designation,
            session=session,
            title=title,
            summary=clean_summary,
            text=summary_text,
            html=summary_html,
            date=doc_date,
            department=None,
            source=Source.JO_JK,
            source_id=source_id,
            source_url=page_url,
            fetched_at=datetime.now(tz=UTC),
            attachments=attachments,
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

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

    async def search(
        self,
        query: str,
        *,
        doc_type: DocType | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search JK decisions via the POST search endpoint.

        Only JK supports search (JO uses sitemap-based discovery with no
        search API).  Returns empty list if doc_type is JO.
        """
        if doc_type and doc_type != DocType.JK:
            return []

        results: list[SearchResult] = []
        page = 1

        while len(results) < limit:
            form_data: dict[str, str | list[str]] = {
                "search": query,
                "diarienummer": "",
                "from-date": "",
                "to-date": "",
                "typ": list(_JK_CATEGORY_IDS),
                "do-search": "",
                "page": str(page),
            }
            html = await self._post_html(_JK_SEARCH_URL, form_data)
            if not html:
                break

            soup = BeautifulSoup(html, "lxml")
            items = self._parse_jk_search_results(soup)
            if not items:
                break

            for item in items:
                if len(results) >= limit:
                    break

                designation = item.get("designation", "")
                date_str = item.get("date")
                doc_date = date.fromisoformat(date_str) if date_str else None
                session = None
                if designation:
                    year_match = re.match(r"(\d{4})/", designation)
                    if year_match:
                        session = year_match.group(1)
                if not session and doc_date:
                    session = str(doc_date.year)

                doc_id = build_doc_id(DocType.JK, designation, session) if designation else ""

                results.append(SearchResult(
                    doc_id=doc_id,
                    doc_type=DocType.JK,
                    title=item["title"],
                    designation=designation,
                    session=session,
                    date=doc_date,
                    source=Source.JO_JK,
                    source_url=item["url"],
                ))

            page += 1

        return results

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
            urls = await self._fetch_jo_sitemap_urls(
                since=since, until=until, limit=limit,
            )
            items = [{"url": u["url"]} for u in urls]
        else:
            items = await self._fetch_jk_listing_urls(
                since=since, until=until, limit=limit,
            )

        count = 0
        for item in items:
            if limit is not None and count >= limit:
                return

            detail_html = await self._fetch_html(item["url"])
            if not detail_html:
                continue

            if doc_type == DocType.JO:
                doc = self._parse_jo_detail_page(detail_html, item["url"])
            else:
                doc = self._parse_jk_detail_page(detail_html, item["url"])
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

        if doc_type == DocType.JO:
            return self._parse_jo_detail_page(html, url)
        return self._parse_jk_detail_page(html, url)
