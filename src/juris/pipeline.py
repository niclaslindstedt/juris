"""Collection pipeline — reusable orchestration for collecting documents."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Protocol

from juris.collectors.base import get_collector_class
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
) -> tuple[int, int]:
    """Run collection for a single (source, doc_type) pair.

    Returns *(collected_count, skipped_count)*.
    """
    src = Source(source_name)
    collector = get_collector_class(source_name)()
    state = load_state(data_dir, src, dt)

    collected = 0
    skipped = 0

    try:
        async for doc in collector.collect(
            dt,
            session=session,
            since=since,
            until=until,
            limit=limit,
            skip_content=skip_content,
        ):
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
    finally:
        if progress:
            progress.on_finish()
        await collector.close()

    save_state(state, data_dir)
    return collected, skipped
