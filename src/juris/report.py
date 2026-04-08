"""Collection coverage reports — generation, persistence, and comparison."""

from __future__ import annotations

import json
import logging
import uuid
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel

from juris.collectors.base import get_preferred_providers
from juris.models import DocType
from juris.state import CollectionState, load_all_states

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DocTypeStats(BaseModel):
    """Statistics for a single document type."""

    doc_type: str
    source: str
    on_disk: int = 0
    date_min: str | None = None
    date_max: str | None = None
    by_year: dict[int, int] = {}
    by_year_pct: dict[int, float] = {}
    last_fetched_date: str | None = None
    last_run_at: str | None = None
    total_collected: int = 0
    total_available: int | None = None


class CollectionReport(BaseModel):
    """A complete collection coverage report."""

    id: str
    generated_at: str
    data_dir: str
    total_documents: int = 0
    total_doc_types: int = 0
    doc_types: list[DocTypeStats] = []


class ReportIndexEntry(BaseModel):
    """One entry in the report index."""

    id: str
    generated_at: str
    total_documents: int
    path: str


class ReportIndex(BaseModel):
    """The full report index, stored at .reports/index.json."""

    entries: list[ReportIndexEntry] = []


class DocTypeDiff(BaseModel):
    """Difference for a single doc_type between two reports."""

    doc_type: str
    on_disk_before: int
    on_disk_after: int
    delta: int
    by_year_delta: dict[int, int] = {}


class ReportDiff(BaseModel):
    """Comparison between two reports."""

    before_id: str
    after_id: str
    before_generated_at: str
    after_generated_at: str
    total_before: int
    total_after: int
    total_delta: int
    doc_types: list[DocTypeDiff] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reports_dir(data_dir: Path) -> Path:
    d = data_dir / ".reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path(data_dir: Path) -> Path:
    return _reports_dir(data_dir) / "index.json"


def _scan_dates(type_dir: Path) -> tuple[int, str | None, str | None, dict[int, int]]:
    """Scan JSON files in *type_dir* and extract date info.

    Returns ``(count, date_min, date_max, year_counts)``.
    """
    year_counts: Counter[int] = Counter()
    date_min: date | None = None
    date_max: date | None = None
    count = 0

    for json_path in type_dir.rglob("*.json"):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            raw_date = data.get("date")
            if not raw_date:
                count += 1
                continue
            d = date.fromisoformat(raw_date)
            count += 1
            year_counts[d.year] += 1
            if date_min is None or d < date_min:
                date_min = d
            if date_max is None or d > date_max:
                date_max = d
        except Exception:
            logger.debug("Skipping unreadable file: %s", json_path)
            count += 1

    return (
        count,
        str(date_min) if date_min else None,
        str(date_max) if date_max else None,
        dict(year_counts),
    )


def _find_state(
    dt: DocType,
    preferred_source: str | None,
    all_states: dict[tuple[str, str], CollectionState],
) -> CollectionState | None:
    """Find the best state entry for a doc type."""
    if preferred_source:
        state = all_states.get((preferred_source, dt.value))
        if state:
            return state
    # Fall back to any state for this doc type
    for (_, dt_val), state in all_states.items():
        if dt_val == dt.value:
            return state
    return None


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def generate_report(data_dir: Path) -> CollectionReport:
    """Scan the data directory and build a coverage report."""
    preferred = get_preferred_providers()
    all_states = load_all_states(data_dir)
    doc_type_stats: list[DocTypeStats] = []
    total = 0

    for dt in DocType:
        source_name = preferred.get(dt.value, "")
        type_dir = data_dir / dt.value

        if type_dir.exists():
            on_disk, date_min, date_max, by_year = _scan_dates(type_dir)
        else:
            on_disk, date_min, date_max, by_year = 0, None, None, {}

        by_year_pct: dict[int, float] = {}
        if on_disk > 0:
            by_year_pct = {yr: round(cnt / on_disk * 100, 1) for yr, cnt in sorted(by_year.items())}

        state = _find_state(dt, source_name, all_states)

        stats = DocTypeStats(
            doc_type=dt.value,
            source=source_name,
            on_disk=on_disk,
            date_min=date_min,
            date_max=date_max,
            by_year=dict(sorted(by_year.items())),
            by_year_pct=by_year_pct,
            last_fetched_date=state.last_fetched_date if state else None,
            last_run_at=state.last_run_at if state else None,
            total_collected=state.total_collected if state else 0,
            total_available=state.total_available if state else None,
        )
        doc_type_stats.append(stats)
        total += on_disk

    return CollectionReport(
        id=str(uuid.uuid4()),
        generated_at=datetime.now(tz=UTC).isoformat(),
        data_dir=str(data_dir.resolve()),
        total_documents=total,
        total_doc_types=sum(1 for s in doc_type_stats if s.on_disk > 0),
        doc_types=doc_type_stats,
    )


def save_report(report: CollectionReport, data_dir: Path) -> Path:
    """Save a report to .reports/ and update the index. Returns the path."""
    reports = _reports_dir(data_dir)
    ts = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H-%M-%S")
    report_path = reports / f"{ts}.json"
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Update index
    idx = _load_index(data_dir)
    idx.entries.append(
        ReportIndexEntry(
            id=report.id,
            generated_at=report.generated_at,
            total_documents=report.total_documents,
            path=f".reports/{report_path.name}",
        )
    )
    _save_index(idx, data_dir)
    return report_path


def _load_index(data_dir: Path) -> ReportIndex:
    path = _index_path(data_dir)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return ReportIndex.model_validate(data)
    return ReportIndex()


def _save_index(index: ReportIndex, data_dir: Path) -> None:
    path = _index_path(data_dir)
    path.write_text(
        json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def list_reports(data_dir: Path) -> list[ReportIndexEntry]:
    """Return all report index entries, newest first."""
    idx = _load_index(data_dir)
    return list(reversed(idx.entries))


def load_report(report_id: str, data_dir: Path) -> CollectionReport | None:
    """Load a report by ID (or unique prefix)."""
    idx = _load_index(data_dir)
    matches = [e for e in idx.entries if e.id.startswith(report_id)]
    if len(matches) != 1:
        return None
    entry = matches[0]
    report_path = data_dir / entry.path
    if not report_path.exists():
        return None
    data = json.loads(report_path.read_text(encoding="utf-8"))
    return CollectionReport.model_validate(data)


def diff_reports(before: CollectionReport, after: CollectionReport) -> ReportDiff:
    """Compute the difference between two reports."""
    before_map = {s.doc_type: s for s in before.doc_types}
    after_map = {s.doc_type: s for s in after.doc_types}
    all_types = sorted(set(before_map) | set(after_map))

    diffs: list[DocTypeDiff] = []
    for dt in all_types:
        b = before_map.get(dt)
        a = after_map.get(dt)
        b_disk = b.on_disk if b else 0
        a_disk = a.on_disk if a else 0
        delta = a_disk - b_disk
        if delta == 0:
            continue

        b_years = b.by_year if b else {}
        a_years = a.by_year if a else {}
        all_years = sorted(set(b_years) | set(a_years))
        year_delta = {
            yr: a_years.get(yr, 0) - b_years.get(yr, 0)
            for yr in all_years
            if a_years.get(yr, 0) - b_years.get(yr, 0) != 0
        }

        diffs.append(
            DocTypeDiff(
                doc_type=dt,
                on_disk_before=b_disk,
                on_disk_after=a_disk,
                delta=delta,
                by_year_delta=year_delta,
            )
        )

    return ReportDiff(
        before_id=before.id,
        after_id=after.id,
        before_generated_at=before.generated_at,
        after_generated_at=after.generated_at,
        total_before=before.total_documents,
        total_after=after.total_documents,
        total_delta=after.total_documents - before.total_documents,
        doc_types=diffs,
    )
