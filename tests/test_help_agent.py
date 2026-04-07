"""Tests for the --help-agent flag."""

from __future__ import annotations

from click.testing import CliRunner

from juris.cli import main
from juris.collectors import get_registry
from juris.models import DocType


def test_help_agent_exits_zero() -> None:
    result = CliRunner().invoke(main, ["--help-agent"])
    assert result.exit_code == 0


def test_help_agent_contains_all_doc_types() -> None:
    result = CliRunner().invoke(main, ["--help-agent"])
    for dt in DocType:
        assert dt.value in result.output, f"Missing doc type: {dt.value}"


def test_help_agent_contains_all_sources() -> None:
    result = CliRunner().invoke(main, ["--help-agent"])
    for source_name in get_registry():
        assert source_name in result.output, f"Missing source: {source_name}"


def test_help_agent_contains_command_syntax() -> None:
    result = CliRunner().invoke(main, ["--help-agent"])
    for keyword in (
        "juris collect",
        "juris collect-type",
        "juris collect-all",
        "juris search",
        "--type",
        "--session",
        "--since",
        "--until",
        "--limit",
        "--data-dir",
    ):
        assert keyword in result.output, f"Missing keyword: {keyword}"


def test_help_agent_no_subcommand_required() -> None:
    """--help-agent should work without a subcommand."""
    result = CliRunner().invoke(main, ["--help-agent"])
    assert result.exit_code == 0
    assert "Missing command" not in result.output
    assert "Error" not in result.output
