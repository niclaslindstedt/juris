"""Collection run logging — structured JSONL per-document log + text file log."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from juris.models import Document

_current_warnings: ContextVar[list[str]] = ContextVar("_current_warnings")


class DocumentStatus(StrEnum):
    """Outcome of processing a single document."""

    OK = "ok"
    OK_WITH_WARNINGS = "ok_with_warnings"
    SKIPPED = "skipped"
    FAILED = "failed"


class DocumentLogEntry(BaseModel):
    """One line in the structured JSONL log."""

    doc_id: str
    doc_type: str
    source: str
    status: DocumentStatus
    warnings: list[str] = []
    error: str | None = None
    path: str | None = None
    timestamp: str


class RunSummary(BaseModel):
    """Written as the last line of the JSONL log (type=summary)."""

    type: str = "summary"
    source: str
    doc_type: str
    started_at: str
    finished_at: str
    total_collected: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    total_warnings: int = 0


# ---------------------------------------------------------------------------
# Warning capture handler — scoped per-document via contextvars
# ---------------------------------------------------------------------------


class _WarningCapture(logging.Handler):
    """Captures WARNING+ records into a contextvar-scoped list.

    This allows concurrent async tasks to each capture their own
    per-document warnings without interference.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.setFormatter(logging.Formatter("%(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            warnings = _current_warnings.get()
        except LookupError:
            return  # no active document scope — ignore
        warnings.append(self.format(record))


# ---------------------------------------------------------------------------
# File-log setup
# ---------------------------------------------------------------------------


def _log_stem(source: str, doc_type: str) -> str:
    """Build a timestamp-based log file stem."""
    ts = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H-%M-%S")
    return f"{ts}_{source}_{doc_type}"


def log_dir_path(data_dir: Path) -> Path:
    """Return (and create) the .logs directory under *data_dir*."""
    d = data_dir / ".logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_file_logging(log_dir: Path, source: str, doc_type: str) -> logging.FileHandler:
    """Add a FileHandler to the root logger that captures everything to a .log file.

    Returns the handler so the caller can remove it when the run is done.
    """
    stem = _log_stem(source, doc_type)
    log_file = log_dir / f"{stem}.log"
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(handler)
    return handler


# ---------------------------------------------------------------------------
# CollectionLogger — structured JSONL + ProgressCallback
# ---------------------------------------------------------------------------


class CollectionLogger:
    """Writes structured JSONL entries and captures per-document warnings.

    Implements the ``ProgressCallback`` protocol used by
    :func:`juris.pipeline.collect_from_source`, plus the extended
    ``begin_document`` / ``end_document`` hooks.
    """

    def __init__(self, log_dir: Path, source: str, doc_type: str) -> None:
        self._source = source
        self._doc_type = doc_type
        self._started_at = datetime.now(tz=UTC).isoformat()

        stem = _log_stem(source, doc_type)
        self._jsonl_path = log_dir / f"{stem}.jsonl"
        self._jsonl_file = open(self._jsonl_path, "a", encoding="utf-8")  # noqa: SIM115

        self._capture = _WarningCapture()
        logging.getLogger().addHandler(self._capture)

        self._token: Token[list[str]] | None = None
        self._current_doc: Document | None = None

        # Counters for run summary
        self._collected = 0
        self._skipped = 0
        self._failed = 0
        self._warned = 0
        self._skipped_ids: set[str] = set()

    # -- Extended hooks (called by pipeline via hasattr) --------------------

    def begin_document(self, doc: Document) -> None:
        """Start capturing warnings for *doc*."""
        self._current_doc = doc
        self._token = _current_warnings.set([])

    def end_document(self, doc_id: str, path: Path | None) -> None:
        """Flush captured warnings and write a JSONL entry."""
        try:
            warnings = _current_warnings.get()
        except LookupError:
            warnings = []

        if self._token is not None:
            _current_warnings.reset(self._token)
            self._token = None

        # Determine status
        if path is None and not self._is_skipped(doc_id):
            status = DocumentStatus.FAILED
            self._failed += 1
        elif self._is_skipped(doc_id):
            status = DocumentStatus.SKIPPED
        elif warnings:
            status = DocumentStatus.OK_WITH_WARNINGS
        else:
            status = DocumentStatus.OK

        if warnings:
            self._warned += len(warnings)

        entry = DocumentLogEntry(
            doc_id=doc_id,
            doc_type=self._doc_type,
            source=self._source,
            status=status,
            warnings=warnings,
            path=str(path) if path else None,
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        self._write_entry(entry)
        self._current_doc = None

    # -- ProgressCallback protocol ------------------------------------------

    def on_save(self, doc_id: str, path: Path) -> None:
        self._collected += 1

    def on_skip(self, doc_id: str) -> None:
        self._skipped += 1
        self._skipped_ids.add(doc_id)

    def on_finish(self) -> None:
        summary = RunSummary(
            source=self._source,
            doc_type=self._doc_type,
            started_at=self._started_at,
            finished_at=datetime.now(tz=UTC).isoformat(),
            total_collected=self._collected,
            total_skipped=self._skipped,
            total_failed=self._failed,
            total_warnings=self._warned,
        )
        self._jsonl_file.write(
            json.dumps(summary.model_dump(), ensure_ascii=False) + "\n"
        )
        self._jsonl_file.close()
        logging.getLogger().removeHandler(self._capture)

    # -- Internal -----------------------------------------------------------

    def _is_skipped(self, doc_id: str) -> bool:
        return doc_id in self._skipped_ids

    def _write_entry(self, entry: DocumentLogEntry) -> None:
        self._jsonl_file.write(
            json.dumps(entry.model_dump(), ensure_ascii=False) + "\n"
        )
        self._jsonl_file.flush()


# ---------------------------------------------------------------------------
# CompositeProgress — forward to multiple callbacks
# ---------------------------------------------------------------------------


class CompositeProgress:
    """Forwards ``ProgressCallback`` calls to two delegates."""

    def __init__(self, ui: object, logger: CollectionLogger) -> None:
        self._ui = ui
        self._logger = logger

    def begin_document(self, doc: Document) -> None:
        self._logger.begin_document(doc)

    def end_document(self, doc_id: str, path: Path | None) -> None:
        self._logger.end_document(doc_id, path)

    def on_save(self, doc_id: str, path: Path) -> None:
        self._logger.on_save(doc_id, path)
        if hasattr(self._ui, "on_save"):
            self._ui.on_save(doc_id, path)
    def on_skip(self, doc_id: str) -> None:
        self._logger.on_skip(doc_id)
        if hasattr(self._ui, "on_skip"):
            self._ui.on_skip(doc_id)
    def on_finish(self) -> None:
        self._logger.on_finish()
        if hasattr(self._ui, "on_finish"):
            self._ui.on_finish()
