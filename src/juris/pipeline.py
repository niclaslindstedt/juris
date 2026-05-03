"""Collection pipeline — reusable orchestration for collecting documents."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol

from juris.collectors.base import get_collector_class
from juris.index import (
    _INDEX_PAGE_SIZE,
    RemoteIndex,
    _doc_to_entry,
    _flush_page,
    load_index,
    save_index,
)
from juris.models import DocType, Source
from juris.state import load_state, save_state
from juris.storage import document_exists, save_document

logger = logging.getLogger(__name__)


class ProgressCallback(Protocol):
    """Optional callback for reporting collection progress.

    Implement this protocol and pass an instance to
    :func:`collect_from_source` to receive progress updates.
    """

    def on_save(self, doc_id: str, path: Path) -> None:
        """Called after a document is saved."""
        ...

    def on_skip(self, doc_id: str) -> None:
        """Called when a document is skipped (already exists)."""
        ...

    def on_finish(self) -> None:
        """Called when the collection loop ends."""
        ...

    # Optional methods (callers use hasattr before invoking):
    #   on_total(total: int) -> None  — fired once when the API-reported
    #       total document count becomes known (typically after page 1).


async def collect_from_source(
    source_name: str,
    dt: DocType,
    data_dir: Path,
    *,
    session: str | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
    skip_existing: bool = True,
    skip_content: bool = False,
    progress: ProgressCallback | None = None,
    update_index: bool = True,
) -> tuple[int, int]:
    """Run collection for a single (source, doc_type) pair.

    Returns *(collected_count, skipped_count)*.

    When ``update_index`` is true (default), the remote index at
    ``.index/{source}_{doc_type}.json`` is populated as a side effect of
    the same enumeration used to download documents — no extra API calls.
    The index is marked ``complete=True`` only when the run had no filters
    (no ``session``, ``since``, ``until``, or ``limit``) so the source was
    fully enumerated.
    """
    src = Source(source_name)
    collector = get_collector_class(source_name)()
    state = load_state(data_dir, src, dt)

    user_since = since  # remember caller's input before auto-incremental fills it in

    # Auto-set since from state for incremental runs
    if since is None and skip_existing and state.last_fetched_date:
        state_date = date.fromisoformat(state.last_fetched_date)
        since = state_date - timedelta(days=2)
        logger.info("Auto-incremental: since=%s (from state minus 2-day buffer)", since)

    collected = 0
    skipped = 0

    # ------------------------------------------------------------------
    # Set up inline remote-index writer (free side effect of enumeration)
    # ------------------------------------------------------------------
    rindex: RemoteIndex | None = None
    seen_index_ids: set[str] = set()
    page_doc_ids: list[str] = []
    page_indexed = 0
    page_dates: list[str] = []
    docs_on_page = 0
    page_num = 0
    if update_index:
        existing = load_index(data_dir, src, dt)
        if existing is not None:
            rindex = existing
            seen_index_ids = {e.doc_id for e in rindex.entries}
            page_num = len(rindex.pages)
        else:
            # Fresh index starts incomplete; only marked complete below if
            # this run is a full enumeration.
            rindex = RemoteIndex(source=src, doc_type=dt, complete=False)

    total_reported = False

    try:
        async for doc in collector.collect(
            dt,
            session=session,
            since=since,
            until=until,
            limit=limit,
            skip_content=skip_content,
        ):
            # Surface API-reported total to the progress UI as soon as it
            # becomes known (typically after the first page response).
            if (
                not total_reported
                and progress is not None
                and collector.total_available is not None
                and hasattr(progress, "on_total")
            ):
                progress.on_total(collector.total_available)
                total_reported = True

            # Update the remote index inline.
            if rindex is not None:
                docs_on_page += 1
                page_doc_ids.append(doc.doc_id)
                page_dates.append(str(doc.date))
                if doc.doc_id not in seen_index_ids:
                    seen_index_ids.add(doc.doc_id)
                    rindex.entries.append(_doc_to_entry(doc))
                    page_indexed += 1
                if docs_on_page >= _INDEX_PAGE_SIZE:
                    _flush_page(rindex, page_num, page_doc_ids, page_indexed, page_dates, data_dir)
                    page_num += 1
                    page_doc_ids = []
                    page_indexed = 0
                    page_dates = []
                    docs_on_page = 0

            if progress and hasattr(progress, "begin_document"):
                progress.begin_document(doc)

            path: Path | None = None
            try:
                exists = document_exists(
                    doc.doc_id,
                    doc.doc_type,
                    doc.session,
                    data_dir,
                )
                if skip_existing and exists:
                    skipped += 1
                    if progress:
                        progress.on_skip(doc.doc_id)
                    continue

                if not skip_content:
                    doc = await collector.download_attachments(doc, data_dir)

                path = save_document(doc, data_dir)
                collected += 1
                if progress:
                    progress.on_save(doc.doc_id, path)

                state.total_collected += 1
                if not state.last_fetched_date or str(doc.date) > state.last_fetched_date:
                    state.last_fetched_date = str(doc.date)
            except Exception:
                logger.exception("Failed to process %s", doc.doc_id)
            finally:
                if progress and hasattr(progress, "end_document"):
                    progress.end_document(doc.doc_id, path)
    finally:
        # Always persist state so that a re-run can skip already-collected
        # documents — even after Ctrl+C or an API failure mid-collection.
        if collector.total_available is not None:
            state.total_available = collector.total_available
        save_state(state, data_dir)

        # Flush remaining partial index page and save the index. We only mark
        # the index complete when the run had no filters — otherwise it
        # represents a partial slice and update_index/another collect run
        # should keep adding to it.
        if rindex is not None:
            if page_doc_ids:
                _flush_page(rindex, page_num, page_doc_ids, page_indexed, page_dates, data_dir)
            if collector.total_available is not None:
                rindex.total_available = collector.total_available
            full_run = user_since is None and until is None and session is None and limit is None
            if full_run:
                rindex.complete = True
                rindex.error = None
                rindex.resume_offset = 0
            save_index(rindex, data_dir)

        if progress:
            progress.on_finish()
        await collector.close()

    return collected, skipped
