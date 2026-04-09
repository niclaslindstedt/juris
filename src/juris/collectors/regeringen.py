"""Regeringen.se scraper (www.regeringen.se/rattsdokument/)."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from urllib.parse import urlencode, urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from juris.collectors.base import BaseCollector
from juris.models import Attachment, DocType, Document, Source
from juris.pdf import extract_ds_designation, extract_lagr_designation
from juris.utils import build_doc_id, extract_page_content, parse_swedish_date

logger = logging.getLogger(__name__)

BASE_URL = "https://www.regeringen.se"

# Map DocType to the URL path segment on Regeringen.se
_DOCTYPE_PATHS: dict[DocType, str] = {
    DocType.PROP: "proposition",
    DocType.SOU: "statens-offentliga-utredningar",
    DocType.DS: "departementsserien-och-promemorior",
    DocType.LAGR: "lagradsremiss",
    DocType.DIR: "kommittedirektiv",
    DocType.SKR: "skrivelse",
}

# Reverse lookup: URL path segment -> DocType
_PATH_TO_DOCTYPE: dict[str, DocType] = {v: k for k, v in _DOCTYPE_PATHS.items()}

# Regex patterns for extracting designation and session from document text.
# Group 1 = session/year, Group 2 = designation number.
_DESIGNATION_PATTERNS: dict[DocType, list[re.Pattern[str]]] = {
    DocType.PROP: [re.compile(r"Prop\.\s*(\d{4}/\d{2}):(\d+)")],
    DocType.SKR: [re.compile(r"Skr\.\s*(\d{4}/\d{2}):(\d+)")],
    DocType.SOU: [re.compile(r"SOU\s+(\d{4}):(\d+)")],
    DocType.DS: [
        re.compile(r"Ds\s+(\d{4}):(\d+)"),
        re.compile(r"ds[- ](\d{4})[- :](\d+)", re.IGNORECASE),
        re.compile(r"ds[- ]?(\d{4})(\d{1,3})(?:\b|/)", re.IGNORECASE),
    ],
    DocType.DIR: [re.compile(r"Dir\.\s*(\d{4}):(\d+)")],
    DocType.LAGR: [
        re.compile(r"Lagrådsremiss\s+(\d{4}):(\d+)"),
    ],
}

# Department reference numbers (e.g., "Fi2026/00780", "Ju2025/01234").
# Used as fallback designation when formal Ds/LAGR numbers are absent
# (common for promemorior and lagrådsremisser).
# Group 1 = department+year, Group 2 = number.
_DEPT_REF_PATTERN = re.compile(r"\b([A-ZÅÄÖa-zåäö]{1,5}\d{4})/(\d{3,6})\b")

PAGE_SIZE = 20  # Regeringen.se shows 20 results per page


def _parse_designation(text: str, doc_type: DocType) -> tuple[str, str | None]:
    """Extract (designation, session) from text containing e.g. 'Prop. 2025/26:229'.

    Returns ("229", "2025/26") for propositions, ("25", "2026") for SOU, etc.
    Falls back to ("", None) if no match is found.
    """
    patterns = _DESIGNATION_PATTERNS.get(doc_type, [])
    for pattern in patterns:
        m = pattern.search(text)
        if m:
            return m.group(2), m.group(1)
    return "", None


def _parse_dept_ref(text: str) -> tuple[str, str | None]:
    """Extract a department reference like 'Fi2026/00780' as (designation, session).

    Returns ("Fi2026/00780", "2026") or ("", None) if no match.
    """
    m = _DEPT_REF_PATTERN.search(text)
    if m:
        full_ref = f"{m.group(1)}/{m.group(2)}"
        # Extract year from the reference (e.g., "2026" from "Fi2026")
        year_match = re.search(r"\d{4}", m.group(1))
        session = year_match.group() if year_match else None
        return full_ref, session
    return "", None


def _infer_doc_type_from_url(url: str) -> DocType | None:
    """Infer the DocType from a Regeringen.se URL path."""
    for path_segment, dt in _PATH_TO_DOCTYPE.items():
        if (
            f"/rattsdokument/{path_segment}/" in url
            or f"/rattsliga-dokument/{path_segment}/" in url
        ):
            return dt
    return None


class RegeringenCollector(BaseCollector):
    """Scrapes documents from Regeringen.se."""

    source = Source.REGERINGEN
    supported_doc_types = list(_DOCTYPE_PATHS.keys())

    def __init__(self, rate_limit: float = 1.0) -> None:
        super().__init__(rate_limit=rate_limit, follow_redirects=True)

    async def _fetch_html(self, url: str) -> str | None:
        """Fetch a URL and return the HTML text, or None on error."""
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

    def _parse_listing_page(self, html: str) -> list[dict[str, str]]:
        """Parse a listing page and return a list of item dicts.

        Each dict has keys: url, title.
        """
        soup = BeautifulSoup(html, "lxml")
        items: list[dict[str, str]] = []

        # Find links that point to detail pages.
        # The site uses /rattsliga-dokument/ (redirected from /rattsdokument/).
        # Detail page links have the pattern: /rattsliga-dokument/<type>/YYYY/MM/<slug>
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not isinstance(href, str):
                continue
            # Match detail page links (not category/filter links)
            if re.match(r"/rattsliga-dokument/[^/]+/\d{4}/\d{2}/", href):
                title = link.get_text(strip=True)
                if title:
                    items.append(
                        {
                            "url": urljoin(BASE_URL, href),
                            "title": title,
                        }
                    )

        return items

    # ------------------------------------------------------------------
    # Detail page parsing
    # ------------------------------------------------------------------

    def _parse_detail_page(self, html: str, page_url: str, doc_type: DocType) -> Document | None:
        """Parse a document detail page into a Document model."""
        soup = BeautifulSoup(html, "lxml")

        # Title: first <h1>
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else ""
        if not title:
            logger.warning("No title found on %s", page_url)
            return None

        # Collect the full page text for designation searching
        page_text = soup.get_text(" ", strip=True)

        # Designation and session
        designation, session = _parse_designation(page_text, doc_type)
        if not designation:
            # Try the <title> tag which often contains "Ds 2026:6" etc.
            title_tag = soup.find("title")
            if title_tag:
                designation, session = _parse_designation(title_tag.get_text(), doc_type)
        if not designation:
            # Try meta tags (og:title, description, keywords)
            for meta_name, meta_val in (
                ("property", "og:title"),
                ("name", "description"),
                ("name", "keywords"),
            ):
                meta_tag = soup.find("meta", attrs={meta_name: meta_val})
                if meta_tag and isinstance(meta_tag, Tag):
                    content = meta_tag.get("content", "")
                    if isinstance(content, str) and content:
                        designation, session = _parse_designation(content, doc_type)
                        if designation:
                            break
        if not designation:
            # Try extracting from the URL slug (e.g. "/ds-20266/")
            designation, session = _parse_designation(page_url, doc_type)
        if not designation:
            # Try department reference number (e.g., "Fi2026/00780") from page text
            designation, session = _parse_dept_ref(page_text)
        if not designation:
            # Try department reference from H1 (often appended to title)
            if h1:
                designation, session = _parse_dept_ref(h1.get_text())
        if not designation:
            # LAGR pages typically lack formal designations — use slug silently.
            # For other types, warn since a designation should normally exist.
            if doc_type != DocType.LAGR:
                logger.warning("Could not parse designation from %s", page_url)
            else:
                logger.debug("No formal designation for lagrådsremiss, using slug: %s", page_url)
            slug = page_url.rstrip("/").rsplit("/", 1)[-1]
            designation = slug

        # Date: look for "Publicerad DD månad YYYY"
        doc_date: date | None = None
        date_match = re.search(r"Publicerad\s+(\d{1,2}\s+\w+\s+\d{4})", page_text)
        if date_match:
            doc_date = parse_swedish_date(date_match.group(1))
        if not doc_date:
            logger.warning("Could not parse date from %s, using today", page_url)
            doc_date = date.today()

        # Department: links to /tx/ paths
        department: str | None = None
        dept_link = soup.find("a", href=re.compile(r"^/tx/\d+"))
        if dept_link and isinstance(dept_link, Tag):
            department = dept_link.get_text(strip=True)

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

        # PDF attachments: links ending in .pdf
        attachments: list[Attachment] = []
        for pdf_link in soup.find_all("a", href=re.compile(r"\.pdf$", re.IGNORECASE)):
            href = pdf_link["href"]
            if not isinstance(href, str):
                continue
            pdf_url = urljoin(BASE_URL, href)
            link_text = pdf_link.get_text(strip=True)

            # Try to extract file size from link text, e.g. "(pdf 2 MB)"
            size_bytes: int | None = None
            size_match = re.search(r"\(pdf\s+([\d,\.]+)\s*(KB|MB|GB)\)", link_text, re.IGNORECASE)
            if size_match:
                size_val = float(size_match.group(1).replace(",", "."))
                unit = size_match.group(2).upper()
                multiplier = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}
                size_bytes = int(size_val * multiplier.get(unit, 1))

            # Derive filename from URL
            filename = pdf_url.rsplit("/", 1)[-1]

            attachments.append(
                Attachment(
                    filename=filename,
                    url=pdf_url,
                    mime_type="application/pdf",
                    size_bytes=size_bytes,
                )
            )

        # Infer session from date when designation parsing didn't provide one
        if not session and doc_date:
            session = str(doc_date.year)

        # Build the source_id from the relative path
        source_id = page_url.replace(BASE_URL, "")

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
            source=Source.REGERINGEN,
            source_id=source_id,
            source_url=page_url,
            fetched_at=datetime.now(tz=UTC),
            attachments=attachments,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def _try_lagr_designation_from_pdf(self, doc: Document) -> Document:
        """For lagrådsremisser, try to extract a better designation from PDF attachments.

        Downloads the first PDF attachment to a temporary location, extracts
        the designation from metadata or first page header, and updates the
        document if a match is found.
        """
        if doc.doc_type != DocType.LAGR:
            return doc

        pdf_attachments = [a for a in doc.attachments if a.mime_type == "application/pdf"]
        if not pdf_attachments:
            return doc

        import tempfile
        from pathlib import Path as _Path

        attachment = pdf_attachments[0]
        try:
            await self._limiter.wait()
            client = await self._get_client()
            resp = await client.get(attachment.url)
            resp.raise_for_status()

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = _Path(tmp.name)

            result = extract_lagr_designation(tmp_path)
            tmp_path.unlink(missing_ok=True)

            if result:
                new_designation, new_session = result
                logger.info(
                    "Extracted lagr designation from PDF: %s (session %s)",
                    new_designation,
                    new_session,
                )
                doc.designation = new_designation
                if new_session:
                    doc.session = new_session
                doc.doc_id = build_doc_id(doc.doc_type, doc.designation, doc.session)

        except (httpx.HTTPError, OSError) as e:
            logger.debug("Could not extract lagr designation from PDF: %s", e)

        return doc

    async def _try_ds_designation_from_pdf(self, doc: Document) -> Document:
        """For DS docs with fallback designations, try to extract from PDF."""
        if doc.doc_type != DocType.DS:
            return doc

        pdf_attachments = [a for a in doc.attachments if a.mime_type == "application/pdf"]
        if not pdf_attachments:
            return doc

        import tempfile
        from pathlib import Path as _Path

        attachment = pdf_attachments[0]
        try:
            await self._limiter.wait()
            client = await self._get_client()
            resp = await client.get(attachment.url)
            resp.raise_for_status()

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = _Path(tmp.name)

            result = extract_ds_designation(tmp_path)
            tmp_path.unlink(missing_ok=True)

            if result:
                new_designation, new_session = result
                logger.info(
                    "Extracted DS designation from PDF: %s (session %s)",
                    new_designation,
                    new_session,
                )
                doc.designation = new_designation
                if new_session:
                    doc.session = new_session
                doc.doc_id = build_doc_id(doc.doc_type, doc.designation, doc.session)

        except (httpx.HTTPError, OSError) as e:
            logger.debug("Could not extract DS designation from PDF: %s", e)

        return doc

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
        """Yield documents from Regeringen.se."""
        if doc_type not in _DOCTYPE_PATHS:
            raise ValueError(f"Unsupported doc type for Regeringen: {doc_type}")

        path = _DOCTYPE_PATHS[doc_type]
        count = 0
        page = 1
        seen_urls: set[str] = set()

        while True:
            # Build listing URL with pagination and optional date filters
            params: dict[str, str] = {"p": str(page)}
            if since:
                params["from"] = since.isoformat()
            if until:
                params["to"] = until.isoformat()

            listing_url = f"{BASE_URL}/rattsliga-dokument/{path}/?{urlencode(params)}"
            logger.info("Fetching listing page %d: %s", page, listing_url)

            html = await self._fetch_html(listing_url)
            if not html:
                break

            items = self._parse_listing_page(html)
            if not items:
                logger.info("No items found on page %d, stopping.", page)
                break

            # Detect pagination loop: if all items on this page were already
            # seen, the site is wrapping around — stop paginating.
            new_on_page = sum(1 for item in items if item["url"] not in seen_urls)
            if new_on_page == 0:
                logger.info("All items on page %d already seen, stopping.", page)
                break

            for item in items:
                if limit and count >= limit:
                    return

                if item["url"] in seen_urls:
                    continue
                seen_urls.add(item["url"])

                logger.info("Fetching detail: %s", item["title"][:60])

                detail_html = await self._fetch_html(item["url"])
                if not detail_html:
                    continue

                doc = self._parse_detail_page(detail_html, item["url"], doc_type)
                if not doc:
                    continue

                # For docs with fallback (slug) designations, try PDF extraction.
                # Skip this when only indexing metadata — it downloads PDFs.
                if not skip_content:
                    is_fallback = len(doc.designation) > 15 or doc.designation.count("-") > 1
                    if doc.attachments and (
                        doc_type == DocType.LAGR or (doc_type == DocType.DS and is_fallback)
                    ):
                        if doc_type == DocType.LAGR:
                            doc = await self._try_lagr_designation_from_pdf(doc)
                        elif doc_type == DocType.DS:
                            doc = await self._try_ds_designation_from_pdf(doc)

                if skip_content:
                    doc.text = None
                    doc.html = None

                # Filter by session if requested
                if session and doc.session != session:
                    continue

                yield doc
                count += 1

            # Stop if we got fewer items than a full page
            if len(items) < PAGE_SIZE:
                break

            page += 1

    async def get_document(self, source_id: str) -> Document | None:
        """Fetch a single document by its relative URL path."""
        url = BASE_URL + source_id
        doc_type = _infer_doc_type_from_url(url)
        if not doc_type:
            logger.warning("Cannot infer doc type from URL: %s", url)
            return None

        html = await self._fetch_html(url)
        if not html:
            return None

        return self._parse_detail_page(html, url, doc_type)
