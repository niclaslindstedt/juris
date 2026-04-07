"""PDF text extraction utilities."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pymupdf

logger = logging.getLogger(__name__)


def extract_text(path: Path) -> str | None:
    """Extract text from a PDF file on disk.

    Returns cleaned plain text, or None if extraction fails.
    """
    try:
        doc = pymupdf.open(path)  # type: ignore[no-untyped-call]
    except Exception:
        logger.warning("Failed to open PDF: %s", path)
        return None
    return _extract_from_doc(doc, str(path))


def extract_text_from_bytes(data: bytes) -> str | None:
    """Extract text from in-memory PDF bytes.

    Returns cleaned plain text, or None if extraction fails.
    """
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception:
        logger.warning("Failed to open PDF from bytes")
        return None
    return _extract_from_doc(doc, "<bytes>")


def extract_lagr_designation(path: Path) -> tuple[str, str | None] | None:
    """Try to extract lagrådsremiss designation from a PDF's metadata or first page.

    Looks for patterns like "Lagrådsremiss 2026:3" or diarienummer patterns
    in PDF metadata (Title, Subject, Keywords) and the first page text.

    Returns (designation, session) tuple or None if not found.
    """
    try:
        doc = pymupdf.open(path)  # type: ignore[no-untyped-call]
    except Exception:
        logger.warning("Failed to open PDF for designation extraction: %s", path)
        return None

    # Pattern for lagrådsremiss-style references
    lagr_re = re.compile(r"Lagrådsremiss\s+(\d{4}):(\d+)", re.IGNORECASE)
    # Diarienummer patterns (e.g. "Ju2026/01234", "Fi2025/00567")
    dnr_re = re.compile(r"\b([A-Z][a-z]?\d{4}/\d{4,6})\b")

    try:
        # Check PDF metadata fields
        metadata = doc.metadata or {}
        for field in ("title", "subject", "keywords", "author"):
            value = metadata.get(field, "") or ""
            m = lagr_re.search(value)
            if m:
                doc.close()  # type: ignore[no-untyped-call]
                return m.group(2), m.group(1)
            m = dnr_re.search(value)
            if m:
                doc.close()  # type: ignore[no-untyped-call]
                dnr = m.group(1)
                year = dnr.split("/")[0][-4:]  # extract year from e.g. "Ju2026"
                return dnr, year

        # Check first page header text (first ~500 chars)
        if len(doc) > 0:
            first_page_text = doc[0].get_text()[:1000]  # type: ignore[no-untyped-call]
            m = lagr_re.search(first_page_text)
            if m:
                doc.close()  # type: ignore[no-untyped-call]
                return m.group(2), m.group(1)
            m = dnr_re.search(first_page_text)
            if m:
                doc.close()  # type: ignore[no-untyped-call]
                dnr = m.group(1)
                year = dnr.split("/")[0][-4:]
                return dnr, year

        doc.close()  # type: ignore[no-untyped-call]
    except Exception:
        logger.warning("Failed to extract designation from PDF: %s", path)
        try:
            doc.close()  # type: ignore[no-untyped-call]
        except Exception:
            pass

    return None


def extract_ds_designation(path: Path) -> tuple[str, str | None] | None:
    """Try to extract DS designation from a PDF's metadata or first page.

    Looks for patterns like "Ds 2026:6" in PDF metadata (Title, Subject, Keywords)
    and the first page text.

    Returns (designation, session) tuple or None if not found.
    """
    try:
        doc = pymupdf.open(path)  # type: ignore[no-untyped-call]
    except Exception:
        logger.warning("Failed to open PDF for DS designation extraction: %s", path)
        return None

    ds_re = re.compile(r"Ds\s+(\d{4}):(\d+)", re.IGNORECASE)

    try:
        # Check PDF metadata fields
        metadata = doc.metadata or {}
        for field in ("title", "subject", "keywords", "author"):
            value = metadata.get(field, "") or ""
            m = ds_re.search(value)
            if m:
                doc.close()  # type: ignore[no-untyped-call]
                return m.group(2), m.group(1)

        # Check first page header text
        if len(doc) > 0:
            first_page_text = doc[0].get_text()[:1000]  # type: ignore[no-untyped-call]
            m = ds_re.search(first_page_text)
            if m:
                doc.close()  # type: ignore[no-untyped-call]
                return m.group(2), m.group(1)

        doc.close()  # type: ignore[no-untyped-call]
    except Exception:
        logger.warning("Failed to extract DS designation from PDF: %s", path)
        try:
            doc.close()  # type: ignore[no-untyped-call]
        except Exception:
            pass

    return None


def _extract_from_doc(doc: pymupdf.Document, label: str) -> str | None:
    """Extract and clean text from an open pymupdf Document."""
    try:
        pages: list[str] = []
        for page in doc:  # type: ignore[attr-defined]
            pages.append(page.get_text())
        doc.close()  # type: ignore[no-untyped-call]
    except Exception:
        logger.warning("Failed to extract text from PDF: %s", label)
        return None

    text = "\n".join(pages)
    # Collapse 3+ consecutive newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    return text if text else None
