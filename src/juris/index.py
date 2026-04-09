"""Remote document index — track what exists on remote sources."""

from __future__ import annotations

import asyncio
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


class PageRecord(BaseModel):
    """Record of a single page/chunk fetched from the source."""

    page: int  # Sequential page number (0-based)
    fetched: int  # Items returned by the API on this page
    indexed: int  # Items actually added to index (after dedup)
    doc_ids: list[str]  # Doc IDs found on this page
    first_date: str | None = None  # Date of first doc on page
    last_date: str | None = None  # Date of last doc on page
    phase: str = "tail"  # "tail" for main enumeration, "front" for front-scan


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
    resume_offset: int = 0  # Docs yielded by collector so far (for efficient resume)
    pages: list[PageRecord] = []  # Page-by-page audit trail


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

    def on_total(self, total: int) -> None:
        """Called when the API-reported total becomes known."""

    def on_status(self, message: str) -> None:
        """Called on phase transitions (e.g. 'saving index')."""

    def on_page(self, page: int, fetched: int, indexed: int) -> None:
        """Called when a page of documents is completed."""

    def on_resume(self, existing_entries: int, existing_pages: int) -> None:
        """Called when resuming from an incomplete index."""

    def on_duplicate(self, doc_id: str) -> None:
        """Called when a duplicate document is skipped."""

    def on_front_scan(self) -> None:
        """Called when starting the front-scan phase."""

    def on_finish(self) -> None:
        """Called when enumeration ends."""


# Default page size for batching documents into page records.
# Matches the most common collector page size.
_INDEX_PAGE_SIZE = 20


def _flush_page(
    index: RemoteIndex,
    page_num: int,
    page_doc_ids: list[str],
    page_indexed: int,
    page_dates: list[str],
    base_dir: Path,
    *,
    phase: str = "tail",
) -> None:
    """Record a completed page and save the index to disk."""
    if not page_doc_ids:
        return
    record = PageRecord(
        page=page_num,
        fetched=len(page_doc_ids),
        indexed=page_indexed,
        doc_ids=page_doc_ids,
        first_date=page_dates[0] if page_dates else None,
        last_date=page_dates[-1] if page_dates else None,
        phase=phase,
    )
    index.pages.append(record)
    save_index(index, base_dir)


async def update_index(
    source_name: str,
    dt: DocType,
    base_dir: Path,
    *,
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
    progress: UpdateProgress | None = None,
    fresh: bool = False,
) -> RemoteIndex:
    """Enumerate remote documents and build a local index.

    Calls the collector with ``skip_content=True`` to enumerate documents
    without downloading full content.  Saves the resulting index to disk
    continuously after each page of results.

    **Resumable**: if a previous run was interrupted (``complete=False``),
    the existing entries are preserved and enumeration resumes from the
    saved offset.  After finishing the tail, a front-scan picks up any
    new documents added since the interrupted run.

    Pass ``fresh=True`` to ignore any existing incomplete index and start
    from scratch.

    Returns the built :class:`RemoteIndex`.
    """
    source = Source(source_name)

    # ------------------------------------------------------------------
    # Load existing index for resume (if applicable)
    # ------------------------------------------------------------------
    entries: list[RemoteEntry] = []
    seen_ids: set[str] = set()
    pages: list[PageRecord] = []
    resume_offset = 0
    resuming = False

    if not fresh:
        existing = load_index(base_dir, source, dt)
        if existing and not existing.complete:
            entries = list(existing.entries)
            seen_ids = {e.doc_id for e in entries}
            pages = list(existing.pages)
            resume_offset = existing.resume_offset
            resuming = True
            logger.info(
                "Resuming %s/%s from offset %d (%d entries, %d pages)",
                source_name,
                dt.value,
                resume_offset,
                len(entries),
                len(pages),
            )
            if progress:
                progress.on_resume(len(entries), len(pages))

    # ------------------------------------------------------------------
    # Phase 1: Finish the tail (resume from offset or start fresh)
    # ------------------------------------------------------------------
    index = RemoteIndex(
        source=source,
        doc_type=dt,
        entries=entries,
        pages=pages,
        resume_offset=resume_offset,
        complete=False,
    )

    collector = get_collector_class(source_name)()
    error_msg: str | None = None
    total_reported = False
    phase1_ok = False
    phase1_new = 0  # new entries discovered during phase 1

    page_num = len(pages)
    page_doc_ids: list[str] = []
    page_indexed = 0
    page_dates: list[str] = []
    docs_on_page = 0
    consecutive_dups = 0  # consecutive duplicate docs (safety valve)

    # Stop after this many consecutive duplicates — the source is likely cycling.
    _DUP_STOP_THRESHOLD = _INDEX_PAGE_SIZE * 5  # 100 consecutive dups

    try:
        async for doc in collector.collect(
            dt,
            since=since,
            until=until,
            limit=limit,
            skip_content=True,
            offset=resume_offset,
        ):
            resume_offset += 1
            index.resume_offset = resume_offset
            docs_on_page += 1

            page_doc_ids.append(doc.doc_id)
            page_dates.append(str(doc.date))

            if progress and not total_reported and collector.total_available is not None:
                progress.on_total(collector.total_available)
                total_reported = True

            if doc.doc_id not in seen_ids:
                seen_ids.add(doc.doc_id)
                entries.append(_doc_to_entry(doc))
                index.entries = entries
                page_indexed += 1
                phase1_new += 1
                consecutive_dups = 0
                if progress:
                    progress.on_found(doc.doc_id)
            else:
                consecutive_dups += 1
                if progress:
                    progress.on_duplicate(doc.doc_id)
                if consecutive_dups >= _DUP_STOP_THRESHOLD:
                    logger.info(
                        "Stopping %s/%s: %d consecutive duplicates — source is cycling",
                        source_name,
                        dt.value,
                        consecutive_dups,
                    )
                    break

            # Flush page record after every _INDEX_PAGE_SIZE docs
            if docs_on_page >= _INDEX_PAGE_SIZE:
                _flush_page(index, page_num, page_doc_ids, page_indexed, page_dates, base_dir)
                if progress:
                    progress.on_page(page_num, docs_on_page, page_indexed)
                page_num += 1
                page_doc_ids = []
                page_indexed = 0
                page_dates = []
                docs_on_page = 0

        phase1_ok = True
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Interrupted — saving partial index for %s/%s", source_name, dt.value)
    except Exception as exc:
        error_msg = str(exc)
        logger.exception("Error enumerating %s/%s", source_name, dt.value)
        if progress:
            progress.on_status("error")
    finally:
        index.total_available = collector.total_available
        await collector.close()

    # Flush remaining partial page
    if page_doc_ids:
        _flush_page(index, page_num, page_doc_ids, page_indexed, page_dates, base_dir)
        if progress:
            progress.on_page(page_num, docs_on_page, page_indexed)

    if not phase1_ok:
        index.error = error_msg
        save_index(index, base_dir)
        if progress:
            progress.on_finish()
        return index

    # ------------------------------------------------------------------
    # Phase 2: Front-scan for new documents (only when resuming)
    # ------------------------------------------------------------------
    if resuming:
        if progress:
            progress.on_front_scan()

        collector2 = get_collector_class(source_name)()
        consecutive_seen = 0
        front_page_num = 0
        front_doc_ids: list[str] = []
        front_indexed = 0
        front_dates: list[str] = []
        front_docs_on_page = 0

        try:
            async for doc in collector2.collect(
                dt,
                since=since,
                until=until,
                skip_content=True,
            ):
                front_docs_on_page += 1
                front_doc_ids.append(doc.doc_id)
                front_dates.append(str(doc.date))

                if doc.doc_id in seen_ids:
                    consecutive_seen += 1
                    if progress:
                        progress.on_duplicate(doc.doc_id)
                else:
                    consecutive_seen = 0
                    seen_ids.add(doc.doc_id)
                    entries.append(_doc_to_entry(doc))
                    index.entries = entries
                    front_indexed += 1
                    if progress:
                        progress.on_found(doc.doc_id)

                # Flush page
                if front_docs_on_page >= _INDEX_PAGE_SIZE:
                    _flush_page(
                        index,
                        page_num + 1 + front_page_num,
                        front_doc_ids,
                        front_indexed,
                        front_dates,
                        base_dir,
                        phase="front",
                    )
                    if progress:
                        progress.on_page(
                            page_num + 1 + front_page_num,
                            front_docs_on_page,
                            front_indexed,
                        )
                    front_page_num += 1
                    front_doc_ids = []
                    front_indexed = 0
                    front_dates = []
                    front_docs_on_page = 0

                # Stop once we've hit a full page of known docs
                if consecutive_seen >= _INDEX_PAGE_SIZE:
                    logger.debug(
                        "Front-scan: hit %d consecutive known docs, stopping",
                        consecutive_seen,
                    )
                    break
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Interrupted during front-scan — saving partial index")
            if front_doc_ids:
                _flush_page(
                    index,
                    page_num + 1 + front_page_num,
                    front_doc_ids,
                    front_indexed,
                    front_dates,
                    base_dir,
                    phase="front",
                )
            index.error = "Interrupted during front-scan"
            save_index(index, base_dir)
            if progress:
                progress.on_finish()
            return index
        except Exception as exc:
            error_msg = str(exc)
            logger.exception("Error during front-scan for %s/%s", source_name, dt.value)
        finally:
            index.total_available = collector2.total_available or index.total_available
            await collector2.close()

        # Flush remaining partial front page
        if front_doc_ids:
            _flush_page(
                index,
                page_num + 1 + front_page_num,
                front_doc_ids,
                front_indexed,
                front_dates,
                base_dir,
                phase="front",
            )

        if error_msg:
            index.error = error_msg
            save_index(index, base_dir)
            if progress:
                progress.on_finish()
            return index

    # ------------------------------------------------------------------
    # Done — mark complete (only if enumeration actually covered the source)
    # ------------------------------------------------------------------
    # Safety check: if we were resuming and phase 1 found nothing new, but
    # total_available is much larger than our entries, the resume likely
    # failed (e.g. offset-based pagination didn't work).  Keep the index
    # incomplete so the next run can retry.
    if (
        resuming
        and phase1_new == 0
        and index.total_available
        and len(entries) < index.total_available * 0.5
    ):
        logger.warning(
            "Resume of %s/%s found 0 new entries but only %d/%d indexed — "
            "keeping incomplete for retry",
            source_name,
            dt.value,
            len(entries),
            index.total_available,
        )
        index.error = "resume stalled — offset-based pagination may have failed"
        save_index(index, base_dir)
        if progress:
            progress.on_status("incomplete")
            progress.on_finish()
        return index

    index.complete = True
    index.error = None
    index.resume_offset = 0

    if progress:
        progress.on_status("saving index")

    save_index(index, base_dir)

    if progress:
        progress.on_status("done")
        progress.on_finish()

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
