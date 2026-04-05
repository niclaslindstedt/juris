"""Incremental collection state tracking."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from juris.models import DocType, Source


class CollectionState(BaseModel):
    """Tracks progress for a specific source + doc_type combination."""

    source: Source
    doc_type: DocType
    last_fetched_date: str | None = None  # ISO date of newest doc seen
    last_page: int = 0
    total_collected: int = 0
    last_run_at: str | None = None  # ISO datetime


def _state_path(base_dir: Path, source: Source, doc_type: DocType) -> Path:
    state_dir = base_dir / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / f"{source.value}_{doc_type.value}.json"


def load_state(base_dir: Path, source: Source, doc_type: DocType) -> CollectionState:
    """Load collection state, returning defaults if none exists."""
    path = _state_path(base_dir, source, doc_type)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return CollectionState.model_validate(data)
    return CollectionState(source=source, doc_type=doc_type)


def save_state(state: CollectionState, base_dir: Path) -> None:
    """Persist collection state to disk."""
    state.last_run_at = datetime.now().isoformat()
    path = _state_path(base_dir, state.source, state.doc_type)
    path.write_text(
        json.dumps(state.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
