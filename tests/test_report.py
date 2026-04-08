"""Tests for the report module and CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from juris.cli import main
from juris.report import (
    CollectionReport,
    DocTypeStats,
    ReportIndex,
    ReportIndexEntry,
    diff_reports,
    generate_report,
    list_reports,
    load_report,
    save_report,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_doc(data_dir: Path, doc_type: str, doc_id: str, doc_date: str) -> Path:
    """Write a minimal document JSON file and return its path."""
    session = doc_date[:4]
    doc_dir = data_dir / doc_type / session
    doc_dir.mkdir(parents=True, exist_ok=True)
    path = doc_dir / f"{doc_id}.json"
    path.write_text(
        json.dumps(
            {
                "doc_id": doc_id,
                "doc_type": doc_type,
                "designation": "1",
                "title": "Test",
                "date": doc_date,
                "source": "riksdagen",
                "fetched_at": "2026-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_state(
    data_dir: Path,
    source: str,
    doc_type: str,
    *,
    total_collected: int = 0,
    total_available: int | None = None,
    last_fetched_date: str | None = None,
    last_run_at: str | None = None,
) -> None:
    """Write a minimal .state file."""
    state_dir = data_dir / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"{source}_{doc_type}.json"
    state_data: dict[str, object] = {
        "source": source,
        "doc_type": doc_type,
        "total_collected": total_collected,
        "last_fetched_date": last_fetched_date,
        "last_run_at": last_run_at,
        "last_page": 0,
    }
    if total_available is not None:
        state_data["total_available"] = total_available
    path.write_text(json.dumps(state_data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_doc_type_stats_defaults(self) -> None:
        s = DocTypeStats(doc_type="prop", source="riksdagen")
        assert s.on_disk == 0
        assert s.by_year == {}
        assert s.date_min is None

    def test_collection_report_roundtrip(self) -> None:
        rpt = CollectionReport(
            id="test-id",
            generated_at="2026-04-08T12:00:00+00:00",
            data_dir="/tmp/data",
            total_documents=100,
            total_doc_types=3,
            doc_types=[
                DocTypeStats(
                    doc_type="prop",
                    source="riksdagen",
                    on_disk=100,
                    by_year={2024: 50, 2025: 50},
                    by_year_pct={2024: 50.0, 2025: 50.0},
                )
            ],
        )
        data = rpt.model_dump(mode="json")
        loaded = CollectionReport.model_validate(data)
        assert loaded.id == rpt.id
        assert loaded.total_documents == 100
        assert loaded.doc_types[0].by_year[2024] == 50

    def test_report_index_empty(self) -> None:
        idx = ReportIndex()
        assert idx.entries == []

    def test_report_index_entry(self) -> None:
        entry = ReportIndexEntry(
            id="abc", generated_at="2026-01-01T00:00:00", total_documents=50, path=".reports/x.json"
        )
        assert entry.id == "abc"


# ---------------------------------------------------------------------------
# generate_report tests
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_empty_data_dir(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        rpt = generate_report(data_dir)
        assert rpt.total_documents == 0
        assert rpt.total_doc_types == 0
        assert len(rpt.doc_types) > 0  # all doc types listed, even empty

    def test_counts_documents(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "prop-1", "2024-01-15")
        _write_doc(data_dir, "prop", "prop-2", "2024-06-20")
        _write_doc(data_dir, "prop", "prop-3", "2025-03-10")

        rpt = generate_report(data_dir)
        assert rpt.total_documents == 3
        assert rpt.total_doc_types == 1

        prop = next(s for s in rpt.doc_types if s.doc_type == "prop")
        assert prop.on_disk == 3
        assert prop.date_min == "2024-01-15"
        assert prop.date_max == "2025-03-10"
        assert prop.by_year == {2024: 2, 2025: 1}
        assert prop.by_year_pct[2024] == pytest.approx(66.7, abs=0.1)
        assert prop.by_year_pct[2025] == pytest.approx(33.3, abs=0.1)

    def test_reads_state(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "prop-1", "2024-01-15")
        _write_state(
            data_dir,
            "riksdagen",
            "prop",
            total_collected=10,
            last_fetched_date="2024-01-15",
            last_run_at="2026-04-01T10:00:00",
        )

        rpt = generate_report(data_dir)
        prop = next(s for s in rpt.doc_types if s.doc_type == "prop")
        assert prop.total_collected == 10
        assert prop.last_fetched_date == "2024-01-15"
        assert prop.last_run_at == "2026-04-01T10:00:00"

    def test_total_available_in_report(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "prop-1", "2024-01-15")
        _write_state(
            data_dir,
            "riksdagen",
            "prop",
            total_collected=10,
            total_available=15432,
            last_fetched_date="2024-01-15",
        )

        rpt = generate_report(data_dir)
        prop = next(s for s in rpt.doc_types if s.doc_type == "prop")
        assert prop.total_available == 15432

    def test_total_available_none_without_state(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "prop-1", "2024-01-15")

        rpt = generate_report(data_dir)
        prop = next(s for s in rpt.doc_types if s.doc_type == "prop")
        assert prop.total_available is None

    def test_backward_compat_state_without_total_available(self, tmp_path: Path) -> None:
        """Old state files without total_available should deserialize cleanly."""
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "prop-1", "2024-01-15")
        # Write state without total_available field
        _write_state(data_dir, "riksdagen", "prop", total_collected=5)

        rpt = generate_report(data_dir)
        prop = next(s for s in rpt.doc_types if s.doc_type == "prop")
        assert prop.total_available is None

    def test_multiple_types(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "prop-1", "2024-01-15")
        _write_doc(data_dir, "sou", "sou-1", "2024-06-01")

        rpt = generate_report(data_dir)
        assert rpt.total_documents == 2
        assert rpt.total_doc_types == 2


# ---------------------------------------------------------------------------
# save/load/list tests
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        rpt = generate_report(data_dir)
        path = save_report(rpt, data_dir)

        assert path.exists()
        assert path.suffix == ".json"

        loaded = load_report(rpt.id, data_dir)
        assert loaded is not None
        assert loaded.id == rpt.id

    def test_list_reports_empty(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        assert list_reports(data_dir) == []

    def test_list_reports_ordering(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        r1 = generate_report(data_dir)
        save_report(r1, data_dir)
        r2 = generate_report(data_dir)
        save_report(r2, data_dir)

        entries = list_reports(data_dir)
        assert len(entries) == 2
        # Newest first
        assert entries[0].id == r2.id
        assert entries[1].id == r1.id

    def test_load_by_prefix(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        rpt = generate_report(data_dir)
        save_report(rpt, data_dir)

        # Load by first 8 chars
        loaded = load_report(rpt.id[:8], data_dir)
        assert loaded is not None
        assert loaded.id == rpt.id

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        assert load_report("nonexistent", data_dir) is None

    def test_index_updated(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        rpt = generate_report(data_dir)
        save_report(rpt, data_dir)

        idx_path = data_dir / ".reports" / "index.json"
        assert idx_path.exists()
        idx = ReportIndex.model_validate(json.loads(idx_path.read_text(encoding="utf-8")))
        assert len(idx.entries) == 1
        assert idx.entries[0].id == rpt.id


# ---------------------------------------------------------------------------
# diff_reports tests
# ---------------------------------------------------------------------------


class TestDiffReports:
    def test_diff_with_changes(self) -> None:
        before = CollectionReport(
            id="before",
            generated_at="2026-04-01T00:00:00",
            data_dir="/tmp",
            total_documents=100,
            doc_types=[
                DocTypeStats(
                    doc_type="prop",
                    source="riksdagen",
                    on_disk=100,
                    by_year={2024: 60, 2025: 40},
                ),
            ],
        )
        after = CollectionReport(
            id="after",
            generated_at="2026-04-08T00:00:00",
            data_dir="/tmp",
            total_documents=150,
            doc_types=[
                DocTypeStats(
                    doc_type="prop",
                    source="riksdagen",
                    on_disk=150,
                    by_year={2024: 80, 2025: 70},
                ),
            ],
        )

        result = diff_reports(before, after)
        assert result.total_delta == 50
        assert len(result.doc_types) == 1
        assert result.doc_types[0].delta == 50
        assert result.doc_types[0].by_year_delta[2024] == 20
        assert result.doc_types[0].by_year_delta[2025] == 30

    def test_diff_no_changes(self) -> None:
        rpt = CollectionReport(
            id="same",
            generated_at="2026-04-01T00:00:00",
            data_dir="/tmp",
            total_documents=100,
            doc_types=[
                DocTypeStats(doc_type="prop", source="riksdagen", on_disk=100),
            ],
        )
        result = diff_reports(rpt, rpt)
        assert result.total_delta == 0
        assert len(result.doc_types) == 0  # no-change types omitted


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestReportCli:
    def test_report_generate(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "prop-1", "2024-01-15")

        runner = CliRunner()
        result = runner.invoke(
            main, ["--data-dir", str(data_dir), "report"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "Collection Report" in result.output
        assert "prop" in result.output

    def test_report_json(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "prop-1", "2024-01-15")

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--data-dir", str(data_dir), "report", "--json"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_documents" in data
        assert data["total_documents"] == 1

    def test_report_list_empty(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(
            main, ["--data-dir", str(data_dir), "report", "list"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "No reports found" in result.output

    def test_report_list_after_generate(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        runner = CliRunner()
        # Generate a report
        runner.invoke(main, ["--data-dir", str(data_dir), "report"], catch_exceptions=False)
        # List it
        result = runner.invoke(
            main, ["--data-dir", str(data_dir), "report", "list"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "ID" in result.output

    def test_report_show(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "prop-1", "2024-01-15")

        rpt = generate_report(data_dir)
        save_report(rpt, data_dir)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--data-dir", str(data_dir), "report", "show", rpt.id[:8]],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Collection Report" in result.output

    def test_report_show_not_found(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--data-dir", str(data_dir), "report", "show", "nonexistent"],
        )
        assert result.exit_code != 0

    def test_report_diff(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "prop-1", "2024-01-15")

        rpt = generate_report(data_dir)
        save_report(rpt, data_dir)

        # Add another doc
        _write_doc(data_dir, "prop", "prop-2", "2024-06-01")

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--data-dir", str(data_dir), "report", "diff", rpt.id[:8]],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "+1" in result.output or "1" in result.output

    def test_report_empty_data_dir(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(
            main, ["--data-dir", str(data_dir), "report"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "0" in result.output


# ---------------------------------------------------------------------------
# collect-all tracker tests
# ---------------------------------------------------------------------------


class TestCollectAllTracker:
    def test_format_elapsed(self) -> None:
        from juris.cli import _format_elapsed

        assert _format_elapsed(5) == "5s"
        assert _format_elapsed(65) == "1m05s"
        assert _format_elapsed(3661) == "1h01m"

    def test_type_result_defaults(self) -> None:
        from juris.cli import _TypeResult

        r = _TypeResult(doc_type="prop", source="riksdagen")
        assert r.status == "pending"
        assert r.collected == 0
        assert r.error is None
