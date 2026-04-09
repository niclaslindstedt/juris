"""Tests for the --debug-agent flag."""

from __future__ import annotations

from click.testing import CliRunner

from juris.cli import main
from juris.collectors import get_registry
from juris.models import DocType


def test_debug_agent_exits_zero() -> None:
    result = CliRunner().invoke(main, ["--debug-agent"])
    assert result.exit_code == 0


def test_debug_agent_contains_all_doc_types() -> None:
    result = CliRunner().invoke(main, ["--debug-agent"])
    for dt in DocType:
        assert dt.value in result.output, f"Missing doc type: {dt.value}"


def test_debug_agent_contains_all_sources() -> None:
    result = CliRunner().invoke(main, ["--debug-agent"])
    for source_name in get_registry():
        assert source_name in result.output, f"Missing source: {source_name}"


def test_debug_agent_contains_debug_info() -> None:
    result = CliRunner().invoke(main, ["--debug-agent"])
    for keyword in (
        ".logs/debug.log",
        ".state/",
        ".reports/",
        "juris logs",
        "--verbose",
        "--failures",
        "juris validate",
    ):
        assert keyword in result.output, f"Missing keyword: {keyword}"


def test_debug_agent_no_subcommand_required() -> None:
    """--debug-agent should work without a subcommand."""
    result = CliRunner().invoke(main, ["--debug-agent"])
    assert result.exit_code == 0
    assert "Missing command" not in result.output
    assert "Error" not in result.output
