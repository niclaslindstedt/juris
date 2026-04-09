"""Tests for the man command."""

from __future__ import annotations

from click.testing import CliRunner

from juris.cli import main


class TestManCommand:
    def test_man_default(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["man"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "juris" in result.output.lower()

    def test_man_collect(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["man", "collect"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "collect" in result.output.lower()

    def test_man_collect_all(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["man", "collect-all"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "collect-all" in result.output.lower()

    def test_man_stats(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["man", "stats"], catch_exceptions=False)
        assert result.exit_code == 0

    def test_man_status(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["man", "status"], catch_exceptions=False)
        assert result.exit_code == 0
