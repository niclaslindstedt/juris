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
        doc = pymupdf.open(path)
    except Exception:
        logger.warning("Failed to open PDF: %s", path)
        return None
    return _extract_from_doc(doc, str(path))


def extract_text_from_bytes(data: bytes) -> str | None:
    """Extract text from in-memory PDF bytes.

    Returns cleaned plain text, or None if extraction fails.
    """
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        logger.warning("Failed to open PDF from bytes")
        return None
    return _extract_from_doc(doc, "<bytes>")


def _extract_from_doc(doc: pymupdf.Document, label: str) -> str | None:
    """Extract and clean text from an open pymupdf Document."""
    try:
        pages: list[str] = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
    except Exception:
        logger.warning("Failed to extract text from PDF: %s", label)
        return None

    text = "\n".join(pages)
    # Collapse 3+ consecutive newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    return text if text else None
