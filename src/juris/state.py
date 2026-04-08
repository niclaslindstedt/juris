"""Incremental collection state tracking."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from juris.models import DocType, Source
from juris.utils import atomic_write_text


class CollectionState(BaseModel):
    """Tracks progress for a specific source + doc_type combination."""

    source: Source
    doc_type: DocType
    last_fetched_date: str | None = None  # ISO date of newest doc seen
    last_page: int = 0
    total_collected: int = 0
    total_available: int | None = None  # API-reported total matching documents
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


def load_all_states(base_dir: Path) -> dict[tuple[str, str], CollectionState]:
    """Load all persisted collection states.

    Returns a dict keyed by ``(source_value, doc_type_value)``.
    """
    state_dir = base_dir / ".state"
    result: dict[tuple[str, str], CollectionState] = {}
    if not state_dir.exists():
        return result
    for path in sorted(state_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        state = CollectionState.model_validate(data)
        result[(state.source.value, state.doc_type.value)] = state
    return result


def save_state(state: CollectionState, base_dir: Path) -> None:
    """Persist collection state to disk."""
    state.last_run_at = datetime.now(tz=UTC).isoformat()
    path = _state_path(base_dir, state.source, state.doc_type)
    atomic_write_text(path, json.dumps(state.model_dump(), ensure_ascii=False, indent=2) + "\n")
