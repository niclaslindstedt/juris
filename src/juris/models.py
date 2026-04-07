"""Unified document models for Swedish legal data."""

from __future__ import annotations

import datetime as _dt
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, model_validator


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
    JO = "jo"  # Justitieombudsmannens beslut
    JK = "jk"  # Justitiekanslerns beslut
    FORESKRIFT = "foreskrift"  # Myndighetsföreskrifter och allmänna råd
    EU_REG = "eu_reg"  # EU regulations (förordningar)
    EU_DIR = "eu_dir"  # EU directives (direktiv)
    CJEU = "cjeu"  # CJEU judgments (EU-domstolen)
    ECHR = "echr"  # ECtHR judgments (Europadomstolen)


class Source(StrEnum):
    """Data sources."""

    RIKSDAGEN = "riksdagen"
    REGERINGEN = "regeringen"
    DOMSTOL = "domstol"
    JO_JK = "jo_jk"
    LAGRUMMET = "lagrummet"
    EUR_LEX = "eur_lex"
    CURIA = "curia"
    HUDOC = "hudoc"


_MIME_ALIASES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "html": "text/html",
    "xml": "application/xml",
    "txt": "text/plain",
}


class Attachment(BaseModel):
    """A file attachment (typically PDF)."""

    filename: str
    url: str
    mime_type: str | None = None
    size_bytes: int | None = None
    local_path: str | None = None  # Relative path to downloaded file

    @model_validator(mode="after")
    def _normalize_mime_type(self) -> Attachment:
        if self.mime_type and self.mime_type in _MIME_ALIASES:
            self.mime_type = _MIME_ALIASES[self.mime_type]
        return self


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


class SearchResult(BaseModel):
    """A search result from local storage or a provider API."""

    doc_id: str
    doc_type: DocType
    title: str
    designation: str = ""
    session: str | None = None
    date: _dt.date | None = None
    source: Source
    source_url: str | None = None
    summary: str | None = None
    snippet: str | None = None  # Text excerpt around match
    local: bool = False  # True if document exists on disk
