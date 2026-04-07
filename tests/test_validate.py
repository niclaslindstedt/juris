"""Unit tests for the validate command."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from juris.cli import main


def _write_doc(data_dir: Path, doc_type: str, filename: str, data: dict) -> Path:
    """Write a JSON document to the data directory."""
    type_dir = data_dir / doc_type
    type_dir.mkdir(parents=True, exist_ok=True)
    path = type_dir / filename
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class TestValidateCommand:
    def test_valid_document(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "test.json", {
            "doc_id": "prop-2024/25:1",
            "doc_type": "prop",
            "designation": "1",
            "title": "En proposition om något viktigt",
            "date": "2024-10-15",
            "source": "riksdagen",
            "text": "This is the full text of the proposition.",
        })

        runner = CliRunner()
        result = runner.invoke(main, ["--data-dir", str(data_dir), "validate"])
        assert result.exit_code == 0
        assert "1 documents checked" in result.output
        assert "0 errors" in result.output
        assert "0 warnings" in result.output

    def test_missing_required_fields(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "bad.json", {
            "doc_id": "",
            "doc_type": "prop",
            "designation": "",
            "title": "",
            "date": "2024-01-01",
            "source": "riksdagen",
        })

        runner = CliRunner()
        result = runner.invoke(main, ["--data-dir", str(data_dir), "validate"])
        assert result.exit_code == 0
        assert "ERROR" in result.output

    def test_duplicate_doc_ids(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        base = {
            "doc_id": "prop-2024/25:1",
            "doc_type": "prop",
            "designation": "1",
            "title": "A proposition",
            "date": "2024-01-01",
            "source": "riksdagen",
            "text": "Some text",
        }
        _write_doc(data_dir, "prop", "doc1.json", base)
        _write_doc(data_dir, "prop", "doc2.json", base)

        runner = CliRunner()
        result = runner.invoke(main, ["--data-dir", str(data_dir), "validate"])
        assert result.exit_code == 0
        assert "Duplicate doc_id" in result.output

    def test_suspicious_date(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "sou", "old.json", {
            "doc_id": "sou-1800:1",
            "doc_type": "sou",
            "designation": "1",
            "title": "Very old document",
            "date": "1800-01-01",
            "source": "riksdagen",
            "text": "Old text",
        })

        runner = CliRunner()
        result = runner.invoke(main, ["--data-dir", str(data_dir), "validate"])
        assert result.exit_code == 0
        assert "Suspiciously old date" in result.output

    def test_missing_content_warning(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "nocontent.json", {
            "doc_id": "prop-2024/25:99",
            "doc_type": "prop",
            "designation": "99",
            "title": "A proposition without content",
            "date": "2024-06-01",
            "source": "riksdagen",
        })

        runner = CliRunner()
        result = runner.invoke(main, ["--data-dir", str(data_dir), "validate"])
        assert result.exit_code == 0
        assert "No text, html, or summary" in result.output

    def test_no_data_dir(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--data-dir", str(tmp_path / "nonexistent"), "validate"])
        assert result.exit_code == 0
        assert "No data directory" in result.output

    def test_type_filter(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        _write_doc(data_dir, "prop", "p1.json", {
            "doc_id": "prop-2024/25:1",
            "doc_type": "prop",
            "designation": "1",
            "title": "A proposition",
            "date": "2024-01-01",
            "source": "riksdagen",
            "text": "text",
        })
        _write_doc(data_dir, "sou", "s1.json", {
            "doc_id": "sou-2024:1",
            "doc_type": "sou",
            "designation": "1",
            "title": "An SOU",
            "date": "2024-01-01",
            "source": "riksdagen",
            "text": "text",
        })

        runner = CliRunner()
        result = runner.invoke(main, ["--data-dir", str(data_dir), "validate", "--type", "prop"])
        assert result.exit_code == 0
        assert "1 documents checked" in result.output
