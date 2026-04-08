"""Tests for document search functionality."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from juris.models import DocType, SearchResult, Source
from juris.search import search_local


def _write_doc(data_dir: Path, doc: dict) -> Path:
    """Write a test document JSON file and return the path."""
    doc_type = doc["doc_type"]
    session = doc.get("session", "2024")
    subdir = data_dir / doc_type / session.replace("/", "-")
    subdir.mkdir(parents=True, exist_ok=True)
    filename = doc["doc_id"].replace("/", "_").replace(":", "_") + ".json"
    path = subdir / filename
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture()
def sample_docs(tmp_path: Path) -> Path:
    """Create a temporary data directory with sample documents."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _write_doc(
        data_dir,
        {
            "doc_id": "jk-2024-1234",
            "doc_type": "jk",
            "designation": "2024/1234",
            "title": "Beslut om yttrandefrihet",
            "summary": "En utredning om yttrandefrihet och tryckfrihet.",
            "text": "Detta beslut rör frågor om yttrandefrihet i media.",
            "date": "2024-03-15",
            "session": "2024",
            "source": "jo_jk",
            "source_id": "/beslut/1234",
            "source_url": "https://www.jk.se/beslut/1234",
            "fetched_at": datetime.now().isoformat(),
        },
    )

    _write_doc(
        data_dir,
        {
            "doc_id": "echr-2023-56789",
            "doc_type": "echr",
            "designation": "56789/20",
            "title": "Case of Smith v. Sweden",
            "summary": "Violation of Article 10 - Freedom of expression.",
            "text": "The applicant alleged a violation of freedom of expression.",
            "date": "2023-06-01",
            "session": "2023",
            "source": "hudoc",
            "source_id": "item-56789",
            "source_url": "https://hudoc.echr.coe.int/eng?i=item-56789",
            "fetched_at": datetime.now().isoformat(),
        },
    )

    _write_doc(
        data_dir,
        {
            "doc_id": "prop-2024-25-100",
            "doc_type": "prop",
            "designation": "100",
            "title": "Proposition om dataskydd",
            "summary": "En proposition om dataskydd och integritet.",
            "text": "Regeringen föreslår nya regler för dataskydd.",
            "date": "2024-11-01",
            "session": "2024/25",
            "source": "riksdagen",
            "source_id": "H503100",
            "source_url": "https://data.riksdagen.se/dokument/H503100",
            "fetched_at": datetime.now().isoformat(),
        },
    )

    return data_dir


class TestSearchResult:
    """Tests for the SearchResult model."""

    def test_create_minimal(self) -> None:
        r = SearchResult(
            doc_id="jk-2024-1",
            doc_type=DocType.JK,
            title="Test",
            source=Source.JO_JK,
        )
        assert r.doc_id == "jk-2024-1"
        assert r.local is False
        assert r.snippet is None

    def test_create_full(self) -> None:
        r = SearchResult(
            doc_id="echr-2023-1",
            doc_type=DocType.ECHR,
            title="Test case",
            designation="12345/20",
            session="2023",
            date=date(2023, 1, 1),
            source=Source.HUDOC,
            source_url="https://example.com",
            summary="A summary",
            snippet="...matched text...",
            local=True,
        )
        assert r.local is True
        assert r.snippet == "...matched text..."
        assert r.date == date(2023, 1, 1)


class TestSearchLocal:
    """Tests for local document search."""

    def test_search_by_title(self, sample_docs: Path) -> None:
        results = search_local("yttrandefrihet", sample_docs)
        assert len(results) >= 1
        assert any(r.doc_id == "jk-2024-1234" for r in results)
        assert all(r.local is True for r in results)

    def test_search_by_designation(self, sample_docs: Path) -> None:
        results = search_local("56789/20", sample_docs)
        assert len(results) == 1
        assert results[0].doc_id == "echr-2023-56789"

    def test_search_by_text(self, sample_docs: Path) -> None:
        results = search_local("dataskydd", sample_docs)
        assert len(results) >= 1
        assert any(r.doc_id == "prop-2024-25-100" for r in results)

    def test_search_by_summary(self, sample_docs: Path) -> None:
        results = search_local("Article 10", sample_docs)
        assert len(results) == 1
        assert results[0].doc_id == "echr-2023-56789"

    def test_search_case_insensitive(self, sample_docs: Path) -> None:
        results = search_local("YTTRANDEFRIHET", sample_docs)
        assert len(results) >= 1

    def test_search_no_results(self, sample_docs: Path) -> None:
        results = search_local("xyznonexistent", sample_docs)
        assert len(results) == 0

    def test_search_filter_by_doc_type(self, sample_docs: Path) -> None:
        results = search_local("yttrandefrihet", sample_docs, doc_type=DocType.JK)
        assert len(results) == 1
        assert results[0].doc_type == DocType.JK

    def test_search_filter_by_source(self, sample_docs: Path) -> None:
        results = search_local("yttrandefrihet", sample_docs, source=Source.JO_JK)
        assert len(results) == 1
        assert results[0].source == Source.JO_JK

    def test_search_limit(self, sample_docs: Path) -> None:
        # Search for a term that matches multiple docs
        results = search_local("20", sample_docs, limit=1)
        assert len(results) <= 1

    def test_search_snippet_generated(self, sample_docs: Path) -> None:
        results = search_local("dataskydd", sample_docs)
        matching = [r for r in results if r.doc_id == "prop-2024-25-100"]
        assert len(matching) == 1
        # Snippet should be generated from summary or text
        assert matching[0].snippet is not None
        assert "dataskydd" in matching[0].snippet.lower()

    def test_search_results_sorted_by_date(self, sample_docs: Path) -> None:
        # Use a broad query that matches multiple docs
        results = search_local("2024", sample_docs)
        dates = [r.date for r in results if r.date]
        assert dates == sorted(dates, reverse=True)

    def test_search_empty_data_dir(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        results = search_local("test", empty_dir)
        assert results == []

    def test_search_nonexistent_data_dir(self, tmp_path: Path) -> None:
        results = search_local("test", tmp_path / "nonexistent")
        assert results == []


class TestSearchCli:
    """Tests for the search CLI command."""

    def test_search_local_only(self, sample_docs: Path) -> None:
        from juris.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--data-dir", str(sample_docs), "search", "yttrandefrihet", "--local-only"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "yttrandefrihet" in result.output.lower()
        assert "result(s)" in result.output

    def test_search_no_results(self, sample_docs: Path) -> None:
        from juris.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--data-dir", str(sample_docs), "search", "xyznonexistent", "--local-only"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "No results found" in result.output

    def test_search_with_type_filter(self, sample_docs: Path) -> None:
        from juris.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--data-dir",
                str(sample_docs),
                "search",
                "yttrandefrihet",
                "--local-only",
                "--type",
                "jk",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "JK" in result.output

    def test_search_conflicting_flags(self, sample_docs: Path) -> None:
        from juris.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--data-dir",
                str(sample_docs),
                "search",
                "test",
                "--local-only",
                "--provider-only",
            ],
        )
        assert result.exit_code != 0
