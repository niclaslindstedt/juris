"""Abstract base collector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

from juris.models import DocType, Document, Source


class BaseCollector(ABC):
    """Base class for all data source collectors."""

    source: Source
    supported_doc_types: list[DocType]

    @abstractmethod
    def collect(
        self,
        doc_type: DocType,
        *,
        session: str | None = None,
        since: date | None = None,
        until: date | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Document]:
        """Yield documents matching the given criteria."""
        ...

    @abstractmethod
    async def get_document(self, source_id: str) -> Document | None:
        """Fetch a single document by its source-specific ID."""
        ...

    async def download_attachments(
        self, doc: Document, base_dir: Path
    ) -> Document:
        """Download attachments and extract text. Override in subclasses."""
        return doc
