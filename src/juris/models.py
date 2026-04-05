"""Unified document models for Swedish legal data."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel


class DocType(StrEnum):
    """Swedish legal document types."""

    PROP = "prop"  # Propositioner (government bills)
    SOU = "sou"  # Statens offentliga utredningar
    MOT = "mot"  # Motioner (parliamentary motions)
    BET = "bet"  # Betänkanden (committee reports)
    DS = "ds"  # Departementsserien (department series)
    LAGR = "lagr"  # Lagrådsremisser (legal council referrals)
    DIR = "dir"  # Kommittédirektiv (committee directives)
    SKR = "skr"  # Skrivelser (government communications)
    SFS = "sfs"  # Svensk författningssamling (Swedish Code of Statutes)
    NJA = "nja"  # Nytt Juridiskt Arkiv (Supreme Court precedents)
    AD = "ad"  # Arbetsdomstolens domar (Labour Court decisions)
    HFD = "hfd"  # Högsta förvaltningsdomstolens årsbok
    MOD = "mod"  # Mark- och miljööverdomstolens avgöranden
    PMOD = "pmod"  # Patent- och marknadsöverdomstolens avgöranden


class Source(StrEnum):
    """Data sources."""

    RIKSDAGEN = "riksdagen"
    REGERINGEN = "regeringen"
    DOMSTOL = "domstol"


class Attachment(BaseModel):
    """A file attachment (typically PDF)."""

    filename: str
    url: str
    mime_type: str | None = None
    size_bytes: int | None = None
    local_path: str | None = None  # Relative path to downloaded file


class Document(BaseModel):
    """A Swedish legal document, unified across all sources."""

    # Identity
    doc_id: str  # Canonical ID, e.g. "prop-2024/25:208"
    doc_type: DocType
    designation: str  # Number/beteckning, e.g. "208"
    session: str | None = None  # Riksmöte, e.g. "2024/25"

    # Content
    title: str
    summary: str | None = None
    text: str | None = None  # Cleaned plain text
    html: str | None = None  # Raw HTML fallback

    # Metadata
    date: date
    department: str | None = None
    committee: str | None = None
    status: str | None = None

    # Source tracking
    source: Source
    source_id: str | None = None  # Original ID from source system
    source_url: str | None = None

    # Collection metadata
    fetched_at: datetime

    # Attachments
    attachments: list[Attachment] = []
