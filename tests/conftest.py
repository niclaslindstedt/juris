"""Shared fixtures and helpers for juris tests."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from juris.models import Document


@pytest.fixture()
def cli_runner() -> CliRunner:
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture()
def tmp_data_dir(tmp_path: Path) -> Path:
    """Temporary data directory for test output."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


def load_saved_documents(data_dir: Path, doc_type: str) -> list[dict]:
    """Load all saved JSON documents for a given doc_type."""
    type_dir = data_dir / doc_type
    if not type_dir.exists():
        return []
    docs = []
    for json_path in sorted(type_dir.rglob("*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        docs.append(data)
    return docs


def load_saved_markdown(data_dir: Path, doc_type: str) -> list[Path]:
    """Return paths to all saved Markdown files for a given doc_type."""
    type_dir = data_dir / doc_type
    if not type_dir.exists():
        return []
    return sorted(type_dir.rglob("*.md"))


def assert_document_quality(
    doc: dict, *, expected_type: str | None = None, expected_source: str | None = None
) -> None:
    """Validate that a saved document meets quality standards.

    Checks required fields, data types, and consistency rules.
    """
    # Required fields must be present and non-empty
    required_fields = ("doc_id", "doc_type", "designation", "title", "date", "source")
    for field in required_fields:
        val = doc.get(field)
        assert val, f"Required field '{field}' is missing or empty in {doc.get('doc_id', '?')}"

    # Type and source consistency
    if expected_type:
        assert doc["doc_type"] == expected_type, (
            f"Expected doc_type={expected_type}, got {doc['doc_type']}"
        )
    if expected_source:
        assert doc["source"] == expected_source, (
            f"Expected source={expected_source}, got {doc['source']}"
        )

    # doc_id must start with the doc_type
    assert doc["doc_id"].startswith(doc["doc_type"]), (
        f"doc_id '{doc['doc_id']}' does not start with doc_type '{doc['doc_type']}'"
    )

    # Title quality
    assert len(doc["title"]) > 3, f"Title too short: '{doc['title']}'"

    # Date must be valid ISO format and not in the future
    doc_date = date.fromisoformat(doc["date"])
    assert doc_date <= date.today(), f"Date is in the future: {doc['date']}"
    assert doc_date.year >= 1900, f"Date year suspiciously old: {doc['date']}"

    # Designation should not be a raw URL or overly long
    assert len(doc["designation"]) <= 200, (
        f"Designation suspiciously long ({len(doc['designation'])} chars)"
    )
    assert not doc["designation"].startswith("http"), (
        f"Designation looks like a URL: {doc['designation']}"
    )

    # Session should be present for most types
    session = doc.get("session")
    if session:
        # Session should look like a year or "YYYY/YY"
        assert re.match(r"^\d{4}(/\d{2})?$", session), f"Session has unexpected format: '{session}'"

    # Pydantic model validation — the document must be loadable
    Document.model_validate(doc)


def assert_markdown_valid(md_path: Path) -> dict:
    """Validate a Markdown file has proper YAML frontmatter. Returns frontmatter dict."""
    content = md_path.read_text(encoding="utf-8")
    assert content.startswith("---\n"), f"Markdown missing frontmatter start: {md_path}"

    # Extract frontmatter
    parts = content.split("---\n", 2)
    assert len(parts) >= 3, f"Markdown missing frontmatter end: {md_path}"
    frontmatter = yaml.safe_load(parts[1])
    assert isinstance(frontmatter, dict), f"Frontmatter is not a dict: {md_path}"
    assert "doc_id" in frontmatter, f"Frontmatter missing doc_id: {md_path}"
    assert "title" in frontmatter, f"Frontmatter missing title: {md_path}"
    return frontmatter


def run_collect(runner: CliRunner, args: list[str], data_dir: Path) -> None:
    """Run a juris CLI command and assert it succeeds."""
    from juris.cli import main

    full_args = ["--data-dir", str(data_dir)] + args
    result = runner.invoke(main, full_args, catch_exceptions=False)
    assert result.exit_code == 0, (
        f"CLI failed with exit code {result.exit_code}\n"
        f"Output: {result.output}\n"
        f"Stderr: {result.stderr if hasattr(result, 'stderr') else 'N/A'}"
    )
