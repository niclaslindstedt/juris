"""Tests for the collection logging module."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime
from pathlib import Path

from click.testing import CliRunner

from juris.logging import (
    CollectionLogger,
    CompositeProgress,
    DocumentLogEntry,
    DocumentStatus,
    RunSummary,
    _current_warnings,
    _WarningCapture,
    log_dir_path,
    setup_file_logging,
)
from juris.models import DocType, Document, Source


def _make_doc(doc_id: str = "prop-2024/25:1", **overrides: object) -> Document:
    """Create a minimal Document for testing."""
    defaults: dict[str, object] = {
        "doc_id": doc_id,
        "doc_type": DocType.PROP,
        "designation": "1",
        "session": "2024/25",
        "title": "Test document",
        "date": date(2024, 1, 1),
        "source": Source.RIKSDAGEN,
        "fetched_at": datetime(2024, 1, 1),
    }
    defaults.update(overrides)
    return Document(**defaults)  # type: ignore[arg-type]


class TestDocumentLogEntry:
    """DocumentLogEntry serialization."""

    def test_serialize_ok(self) -> None:
        entry = DocumentLogEntry(
            doc_id="prop-2024/25:1",
            doc_type="prop",
            source="riksdagen",
            status=DocumentStatus.OK,
            timestamp="2024-01-01T00:00:00+00:00",
        )
        data = entry.model_dump()
        assert data["status"] == "ok"
        assert data["warnings"] == []
        assert data["error"] is None

    def test_serialize_with_warnings(self) -> None:
        entry = DocumentLogEntry(
            doc_id="prop-2024/25:1",
            doc_type="prop",
            source="riksdagen",
            status=DocumentStatus.OK_WITH_WARNINGS,
            warnings=["HTTP 429 for URL, retrying", "Timeout downloading PDF"],
            timestamp="2024-01-01T00:00:00+00:00",
        )
        data = entry.model_dump()
        assert data["status"] == "ok_with_warnings"
        assert len(data["warnings"]) == 2

    def test_roundtrip_json(self) -> None:
        entry = DocumentLogEntry(
            doc_id="prop-2024/25:1",
            doc_type="prop",
            source="riksdagen",
            status=DocumentStatus.FAILED,
            error="Connection refused",
            timestamp="2024-01-01T00:00:00+00:00",
        )
        line = json.dumps(entry.model_dump())
        restored = DocumentLogEntry.model_validate(json.loads(line))
        assert restored == entry


class TestRunSummary:
    """RunSummary serialization."""

    def test_has_type_field(self) -> None:
        summary = RunSummary(
            source="riksdagen",
            doc_type="prop",
            started_at="2024-01-01T00:00:00+00:00",
            finished_at="2024-01-01T00:01:00+00:00",
            total_collected=10,
            total_skipped=5,
        )
        data = summary.model_dump()
        assert data["type"] == "summary"
        assert data["total_collected"] == 10


class TestWarningCapture:
    """_WarningCapture handler captures warnings into contextvar."""

    def test_captures_warnings(self) -> None:
        handler = _WarningCapture()
        token = _current_warnings.set([])
        try:
            logger = logging.getLogger("test.capture")
            logger.addHandler(handler)
            logger.warning("something went wrong")
            warnings = _current_warnings.get()
            assert len(warnings) == 1
            assert "something went wrong" in warnings[0]
        finally:
            logger.removeHandler(handler)
            _current_warnings.reset(token)

    def test_ignores_without_context(self) -> None:
        """Warnings emitted outside a document scope are silently ignored."""
        handler = _WarningCapture()
        logger = logging.getLogger("test.no_context")
        logger.addHandler(handler)
        try:
            logger.warning("orphan warning")
            # Should not raise — just ignored
        finally:
            logger.removeHandler(handler)

    def test_does_not_capture_info(self) -> None:
        handler = _WarningCapture()
        token = _current_warnings.set([])
        try:
            logger = logging.getLogger("test.info")
            logger.addHandler(handler)
            logger.info("just info")
            warnings = _current_warnings.get()
            assert len(warnings) == 0
        finally:
            logger.removeHandler(handler)
            _current_warnings.reset(token)

    def test_contextvar_isolation(self) -> None:
        """Different contextvar tokens get independent warning lists."""
        handler = _WarningCapture()
        logger = logging.getLogger("test.isolation")
        logger.addHandler(handler)

        async def _task(msg: str) -> list[str]:
            token = _current_warnings.set([])
            try:
                logger.warning(msg)
                return list(_current_warnings.get())
            finally:
                _current_warnings.reset(token)

        async def _run() -> tuple[list[str], list[str]]:
            r1, r2 = await asyncio.gather(_task("task-a"), _task("task-b"))
            return r1, r2

        try:
            a, b = asyncio.run(_run())
            assert len(a) == 1
            assert "task-a" in a[0]
            assert len(b) == 1
            assert "task-b" in b[0]
        finally:
            logger.removeHandler(handler)


class TestCollectionLogger:
    """CollectionLogger writes valid JSONL entries."""

    def test_writes_ok_entry(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".logs"
        log_dir.mkdir()
        cl = CollectionLogger(log_dir, "riksdagen", "prop")
        doc = _make_doc()

        cl.begin_document(doc)
        cl.on_save(doc.doc_id, Path("data/prop/2024-25/prop-2024-25_1.json"))
        cl.end_document(doc.doc_id, Path("data/prop/2024-25/prop-2024-25_1.json"))
        cl.on_finish()

        jsonl_files = list(log_dir.glob("*.jsonl"))
        assert len(jsonl_files) == 1
        lines = jsonl_files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2  # 1 entry + 1 summary

        entry = json.loads(lines[0])
        assert entry["status"] == "ok"
        assert entry["doc_id"] == "prop-2024/25:1"
        assert entry["warnings"] == []

        summary = json.loads(lines[1])
        assert summary["type"] == "summary"
        assert summary["total_collected"] == 1

    def test_writes_warning_entry(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".logs"
        log_dir.mkdir()
        cl = CollectionLogger(log_dir, "riksdagen", "prop")
        doc = _make_doc()

        cl.begin_document(doc)
        # Simulate a warning from a collector
        logging.getLogger("juris.collectors.riksdagen").warning("HTTP 429 for test-url")
        cl.on_save(doc.doc_id, Path("data/prop/test.json"))
        cl.end_document(doc.doc_id, Path("data/prop/test.json"))
        cl.on_finish()

        jsonl_files = list(log_dir.glob("*.jsonl"))
        lines = jsonl_files[0].read_text(encoding="utf-8").strip().splitlines()
        entry = json.loads(lines[0])
        assert entry["status"] == "ok_with_warnings"
        assert len(entry["warnings"]) == 1
        assert "429" in entry["warnings"][0]

    def test_writes_skip_entry(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".logs"
        log_dir.mkdir()
        cl = CollectionLogger(log_dir, "riksdagen", "prop")
        doc = _make_doc()

        cl.begin_document(doc)
        cl.on_skip(doc.doc_id)
        cl.end_document(doc.doc_id, None)
        cl.on_finish()

        jsonl_files = list(log_dir.glob("*.jsonl"))
        lines = jsonl_files[0].read_text(encoding="utf-8").strip().splitlines()
        entry = json.loads(lines[0])
        assert entry["status"] == "skipped"

        summary = json.loads(lines[1])
        assert summary["total_skipped"] == 1

    def test_writes_failed_entry(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".logs"
        log_dir.mkdir()
        cl = CollectionLogger(log_dir, "riksdagen", "prop")
        doc = _make_doc()

        cl.begin_document(doc)
        cl.end_document(doc.doc_id, None)  # path=None and not skipped => failed
        cl.on_finish()

        jsonl_files = list(log_dir.glob("*.jsonl"))
        lines = jsonl_files[0].read_text(encoding="utf-8").strip().splitlines()
        entry = json.loads(lines[0])
        assert entry["status"] == "failed"

        summary = json.loads(lines[1])
        assert summary["total_failed"] == 1


class TestCompositeProgress:
    """CompositeProgress forwards to both delegates."""

    def test_forwards_on_save(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".logs"
        log_dir.mkdir()
        cl = CollectionLogger(log_dir, "riksdagen", "prop")

        calls: list[str] = []

        class FakeUI:
            def on_save(self, doc_id: str, path: Path) -> None:
                calls.append(f"save:{doc_id}")

            def on_skip(self, doc_id: str) -> None:
                calls.append(f"skip:{doc_id}")

            def on_finish(self) -> None:
                calls.append("finish")

        composite = CompositeProgress(FakeUI(), cl)
        doc = _make_doc()
        p = Path("data/test.json")

        composite.begin_document(doc)
        composite.on_save(doc.doc_id, p)
        composite.end_document(doc.doc_id, p)
        composite.on_finish()

        assert "save:prop-2024/25:1" in calls
        assert "finish" in calls

    def test_forwards_on_skip(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".logs"
        log_dir.mkdir()
        cl = CollectionLogger(log_dir, "riksdagen", "prop")

        calls: list[str] = []

        class FakeUI:
            def on_save(self, doc_id: str, path: Path) -> None:
                calls.append(f"save:{doc_id}")

            def on_skip(self, doc_id: str) -> None:
                calls.append(f"skip:{doc_id}")

            def on_finish(self) -> None:
                calls.append("finish")

        composite = CompositeProgress(FakeUI(), cl)
        doc = _make_doc()

        composite.begin_document(doc)
        composite.on_skip(doc.doc_id)
        composite.end_document(doc.doc_id, None)
        composite.on_finish()

        assert "skip:prop-2024/25:1" in calls


class TestSetupFileLogging:
    """setup_file_logging creates a log file and captures output."""

    def test_creates_log_file(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".logs"
        log_dir.mkdir()
        handler = setup_file_logging(log_dir, "riksdagen", "prop")
        try:
            logging.getLogger("test.file_log").warning("test message")
            handler.flush()
            log_files = list(log_dir.glob("*.log"))
            assert len(log_files) == 1
            content = log_files[0].read_text(encoding="utf-8")
            assert "test message" in content
        finally:
            logging.getLogger().removeHandler(handler)
            handler.close()


class TestLogDirPath:
    """log_dir_path creates the directory."""

    def test_creates_logs_dir(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        result = log_dir_path(data_dir)
        assert result == data_dir / ".logs"
        assert result.exists()


class TestLogsCommand:
    """Test the `juris logs` CLI command."""

    def _write_jsonl(self, log_dir: Path, stem: str, entries: list[dict]) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{stem}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    def test_no_logs(self, tmp_path: Path) -> None:
        from juris.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--data-dir", str(tmp_path), "logs"])
        assert result.exit_code == 0
        assert "No logs found" in result.output

    def test_list_runs(self, tmp_path: Path) -> None:
        from juris.cli import main

        log_dir = tmp_path / ".logs"
        self._write_jsonl(log_dir, "2026-04-07T14-30-00_riksdagen_prop", [
            {"doc_id": "prop-2024/25:1", "status": "ok", "doc_type": "prop",
             "source": "riksdagen", "warnings": [], "timestamp": "2026-04-07T14:30:00+00:00"},
            {"type": "summary", "source": "riksdagen", "doc_type": "prop",
             "started_at": "2026-04-07T14:30:00+00:00",
             "finished_at": "2026-04-07T14:31:00+00:00",
             "total_collected": 1, "total_skipped": 0,
             "total_failed": 0, "total_warnings": 0},
        ])

        runner = CliRunner()
        result = runner.invoke(main, ["--data-dir", str(tmp_path), "logs"])
        assert result.exit_code == 0
        assert "riksdagen_prop" in result.output

    def test_filter_by_source(self, tmp_path: Path) -> None:
        from juris.cli import main

        log_dir = tmp_path / ".logs"
        self._write_jsonl(log_dir, "2026-04-07T14-30-00_riksdagen_prop", [
            {"type": "summary", "source": "riksdagen", "doc_type": "prop",
             "started_at": "x", "finished_at": "x",
             "total_collected": 5, "total_skipped": 0,
             "total_failed": 0, "total_warnings": 0},
        ])
        self._write_jsonl(log_dir, "2026-04-07T14-30-00_hudoc_echr", [
            {"type": "summary", "source": "hudoc", "doc_type": "echr",
             "started_at": "x", "finished_at": "x",
             "total_collected": 3, "total_skipped": 0,
             "total_failed": 0, "total_warnings": 0},
        ])

        runner = CliRunner()
        result = runner.invoke(main, ["--data-dir", str(tmp_path), "logs", "--source", "riksdagen"])
        assert result.exit_code == 0
        assert "riksdagen_prop" in result.output
        assert "hudoc_echr" not in result.output

    def test_show_run(self, tmp_path: Path) -> None:
        from juris.cli import main

        log_dir = tmp_path / ".logs"
        self._write_jsonl(log_dir, "2026-04-07T14-30-00_riksdagen_prop", [
            {"doc_id": "prop-2024/25:1", "status": "ok", "doc_type": "prop",
             "source": "riksdagen", "warnings": [], "timestamp": "x"},
            {"doc_id": "prop-2024/25:2", "status": "failed", "doc_type": "prop",
             "source": "riksdagen", "warnings": [], "error": "timeout",
             "timestamp": "x"},
            {"type": "summary", "source": "riksdagen", "doc_type": "prop",
             "started_at": "x", "finished_at": "x",
             "total_collected": 1, "total_skipped": 0,
             "total_failed": 1, "total_warnings": 0},
        ])

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--data-dir", str(tmp_path), "logs", "--run", "riksdagen_prop"],
        )
        assert result.exit_code == 0
        assert "prop-2024/25:1" in result.output
        assert "prop-2024/25:2" in result.output

    def test_failures_filter(self, tmp_path: Path) -> None:
        from juris.cli import main

        log_dir = tmp_path / ".logs"
        self._write_jsonl(log_dir, "2026-04-07T14-30-00_riksdagen_prop", [
            {"doc_id": "prop-2024/25:1", "status": "ok", "doc_type": "prop",
             "source": "riksdagen", "warnings": [], "timestamp": "x"},
            {"doc_id": "prop-2024/25:2", "status": "failed", "doc_type": "prop",
             "source": "riksdagen", "warnings": ["retry failed"],
             "error": "timeout", "timestamp": "x"},
            {"type": "summary", "source": "riksdagen", "doc_type": "prop",
             "started_at": "x", "finished_at": "x",
             "total_collected": 1, "total_skipped": 0,
             "total_failed": 1, "total_warnings": 1},
        ])

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--data-dir", str(tmp_path), "logs", "--run", "riksdagen_prop", "--failures"],
        )
        assert result.exit_code == 0
        assert "prop-2024/25:2" in result.output
        # The OK document should be filtered out
        assert "prop-2024/25:1" not in result.output
