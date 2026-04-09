"""Remote document index — track what exists on remote sources."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel

from juris.collectors.base import get_collector_class
from juris.models import DocType, Document, Source
from juris.storage import document_exists
from juris.utils import atomic_write_text

logger = logging.getLogger(__name__)


class RemoteEntry(BaseModel):
    """Lightweight reference to a remote document."""

    doc_id: str
    doc_type: DocType
    designation: str
    title: str
    date: str  # ISO date
    session: str | None = None
    source: Source
    source_url: str | None = None


class RemoteIndex(BaseModel):
    """Index of known remote documents for a source + doc_type pair."""

    source: Source
    doc_type: DocType
    entries: list[RemoteEntry] = []
    total_entries: int = 0
    total_available: int | None = None  # API-reported total (if source provides it)
    complete: bool = True  # False if enumeration was interrupted or errored
    error: str | None = None  # Error message if enumeration failed
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _index_dir(base_dir: Path) -> Path:
    d = base_dir / ".index"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path(base_dir: Path, source: Source, doc_type: DocType) -> Path:
    return _index_dir(base_dir) / f"{source.value}_{doc_type.value}.json"


def save_index(index: RemoteIndex, base_dir: Path) -> Path:
    """Persist a remote index to disk. Returns the file path."""
    index.updated_at = datetime.now(tz=UTC).isoformat()
    index.total_entries = len(index.entries)
    path = _index_path(base_dir, index.source, index.doc_type)
    atomic_write_text(
        path,
        json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
    )
    return path


def load_index(base_dir: Path, source: Source, doc_type: DocType) -> RemoteIndex | None:
    """Load a remote index, returning None if it doesn't exist."""
    path = _index_path(base_dir, source, doc_type)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return RemoteIndex.model_validate(data)


def load_all_indexes(base_dir: Path) -> dict[tuple[str, str], RemoteIndex]:
    """Load all persisted remote indexes.

    Returns a dict keyed by ``(source_value, doc_type_value)``.
    """
    idx_dir = base_dir / ".index"
    result: dict[tuple[str, str], RemoteIndex] = {}
    if not idx_dir.exists():
        return result
    for path in sorted(idx_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            index = RemoteIndex.model_validate(data)
            result[(index.source.value, index.doc_type.value)] = index
        except Exception:
            logger.debug("Skipping unreadable index file: %s", path)
    return result


# ---------------------------------------------------------------------------
# Update logic
# ---------------------------------------------------------------------------


def _doc_to_entry(doc: Document) -> RemoteEntry:
    return RemoteEntry(
        doc_id=doc.doc_id,
        doc_type=doc.doc_type,
        designation=doc.designation,
        title=doc.title,
        date=str(doc.date),
        session=doc.session,
        source=doc.source,
        source_url=doc.source_url,
    )


class UpdateProgress:
    """Protocol-like callback for update progress."""

    def on_found(self, doc_id: str) -> None:
        """Called when a remote document is discovered."""

    def on_finish(self) -> None:
        """Called when enumeration ends."""


async def update_index(
    source_name: str,
    dt: DocType,
    base_dir: Path,
    *,
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
    progress: UpdateProgress | None = None,
) -> RemoteIndex:
    """Enumerate remote documents and build a local index.

    Calls the collector with ``skip_content=True`` to enumerate documents
    without downloading full content. Saves the resulting index to disk.

    If enumeration completes normally, ``complete`` is ``True``.
    If an error occurs mid-enumeration, the partial index is saved with
    ``complete=False`` and the error message recorded.
    If the user cancels (Ctrl+C), no index is saved.

    Returns the built :class:`RemoteIndex`.
    """
    collector = get_collector_class(source_name)()
    entries: list[RemoteEntry] = []
    seen_ids: set[str] = set()
    complete = True
    error_msg: str | None = None

    try:
        async for doc in collector.collect(
            dt,
            since=since,
            until=until,
            limit=limit,
            skip_content=True,
        ):
            if doc.doc_id in seen_ids:
                continue
            seen_ids.add(doc.doc_id)
            entries.append(_doc_to_entry(doc))
            if progress:
                progress.on_found(doc.doc_id)
    except Exception as exc:
        complete = False
        error_msg = str(exc)
        logger.exception("Error enumerating %s/%s", source_name, dt.value)
    finally:
        total_available = collector.total_available
        if progress:
            progress.on_finish()
        await collector.close()

    index = RemoteIndex(
        source=Source(source_name),
        doc_type=dt,
        entries=entries,
        total_available=total_available,
        complete=complete,
        error=error_msg,
    )
    save_index(index, base_dir)
    return index


async def update_counts(
    source_name: str,
    dt: DocType,
    base_dir: Path,
) -> RemoteIndex:
    """Quick update: fetch only the API-reported total without enumerating.

    Makes a single request (``limit=1``) to get ``total_available`` from the
    source.  If an existing index is on disk, its entries are preserved and
    only the ``total_available`` and ``updated_at`` fields are refreshed.
    """
    collector = get_collector_class(source_name)()

    try:
        # Fetch a single document to trigger the API's total count
        async for _doc in collector.collect(dt, limit=1, skip_content=True):
            break  # one is enough
    except Exception:
        logger.debug("Could not fetch counts for %s/%s", source_name, dt.value)
    finally:
        total_available = collector.total_available
        await collector.close()

    existing = load_index(base_dir, Source(source_name), dt)
    if existing:
        existing.total_available = total_available
        save_index(existing, base_dir)
        return existing

    index = RemoteIndex(
        source=Source(source_name),
        doc_type=dt,
        total_available=total_available,
    )
    save_index(index, base_dir)
    return index


def entries_by_year(index: RemoteIndex) -> dict[int, int]:
    """Count index entries per year from their dates."""
    counts: dict[int, int] = {}
    for entry in index.entries:
        try:
            year = int(entry.date[:4])
            counts[year] = counts.get(year, 0) + 1
        except (ValueError, IndexError):
            pass
    return dict(sorted(counts.items()))


def count_local(doc_type: DocType, base_dir: Path) -> int:
    """Count collected documents on disk for a doc type."""
    type_dir = base_dir / doc_type.value
    if not type_dir.exists():
        return 0
    return len(list(type_dir.rglob("*.json")))


def count_missing(index: RemoteIndex, base_dir: Path) -> int:
    """Count remote entries that are NOT present locally."""
    missing = 0
    for entry in index.entries:
        if not document_exists(entry.doc_id, entry.doc_type, entry.session, base_dir):
            missing += 1
    return missing
