"""CLI entry point for juris."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time
from datetime import date
from pathlib import Path

import click

from juris.collectors import (
    get_collector_class,
    get_doc_type_providers,
    get_preferred_providers,
    get_registry,
    get_searchable_sources,
)
from juris.logging import CollectionLogger, CompositeProgress, log_dir_path, setup_file_logging
from juris.models import DocType, SearchResult, Source
from juris.pipeline import collect_from_source
from juris.report import CollectionReport, ReportDiff

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path("data")

# Resolved at import time (auto-discovery has already run).
_COLLECTOR_NAMES = sorted(get_registry().keys())

# English descriptions for each document type (enum comments aren't accessible at runtime).
_DOC_TYPE_DESCRIPTIONS: dict[str, str] = {
    "prop": "Government bills (propositioner)",
    "sou": "Government inquiries (statens offentliga utredningar)",
    "mot": "Parliamentary motions (motioner)",
    "bet": "Committee reports (betänkanden)",
    "ds": "Department series (departementsserien)",
    "lagr": "Legal council referrals (lagrådsremisser)",
    "dir": "Committee directives (kommittédirektiv)",
    "skr": "Government communications (skrivelser)",
    "sfs": "Swedish Code of Statutes (svensk författningssamling)",
    "nja": "Supreme Court precedents (Nytt Juridiskt Arkiv)",
    "ad": "Labour Court decisions (Arbetsdomstolen)",
    "hfd": "Supreme Administrative Court yearbook (HFD)",
    "mod": "Land & Environment Court of Appeal decisions (MÖD)",
    "pmod": "Patent & Market Court of Appeal decisions (PMÖD)",
    "jo": "Parliamentary Ombudsman decisions (JO)",
    "jk": "Chancellor of Justice decisions (JK)",
    "foreskrift": "Regulatory agency rules (myndighetsföreskrifter)",
    "eu_reg": "EU regulations (förordningar)",
    "eu_dir": "EU directives (direktiv)",
    "cjeu": "CJEU judgments (EU-domstolen)",
    "echr": "ECtHR judgments against Sweden (Europadomstolen)",
}


def _generate_agent_help() -> str:
    """Build a concise reference prompt for AI agents using juris."""
    registry = get_registry()
    preferred = get_preferred_providers()
    searchable = get_searchable_sources()

    lines: list[str] = []
    lines.append("# juris — Swedish legal data collection CLI")
    lines.append("")
    lines.append("Collects and stores Swedish legal documents from 8 public sources")
    lines.append("as JSON + Markdown files. Use `--data-dir DIR` to set the output directory")
    lines.append("(default: `data`).")
    lines.append("")

    # Document types
    lines.append("## Document types")
    lines.append("")
    for dt in DocType:
        desc = _DOC_TYPE_DESCRIPTIONS.get(dt.value, "")
        lines.append(f"- `{dt.value}` — {desc}")
    lines.append("")

    # Sources and supported types
    lines.append("## Sources")
    lines.append("")
    for source_name in sorted(registry.keys()):
        cls = registry[source_name]
        types = ", ".join(t.value for t in cls.supported_doc_types)
        search_note = " (supports search)" if source_name in searchable else ""
        lines.append(f"- `{source_name}`: {types}{search_note}")
    lines.append("")

    # Preferred providers
    lines.append("## Preferred providers")
    lines.append("")
    lines.append("When multiple sources support the same type, the preferred provider is:")
    lines.append("")
    for dt_val, source_name in sorted(preferred.items()):
        lines.append(f"- `{dt_val}` <- `{source_name}`")
    lines.append("")

    # Commands
    lines.append("## Commands")
    lines.append("")
    lines.append("### collect — Collect from a specific source")
    lines.append("```")
    lines.append(
        "juris collect <source> --type <doc_type> [--session SESSION] "
        "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--limit N] "
        "[--skip-content] [--no-skip-existing]"
    )
    lines.append("```")
    lines.append("")
    lines.append("### collect-type — Collect using the best provider")
    lines.append("```")
    lines.append(
        "juris collect-type <doc_type> [--session SESSION] "
        "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--limit N] "
        "[--all-providers] [--dry-run]"
    )
    lines.append("```")
    lines.append("")
    lines.append("### collect-all — Collect all types from best providers")
    lines.append("```")
    lines.append(
        "juris collect-all [--since YYYY-MM-DD] [--until YYYY-MM-DD] "
        "[--limit N] [--concurrent] [--dry-run]"
    )
    lines.append("```")
    lines.append("")
    lines.append("### search — Search for documents by keyword")
    lines.append("```")
    lines.append(
        "juris search <query> [--source SOURCE] [--type DOC_TYPE] "
        "[--local-only] [--provider-only] [--limit N]"
    )
    lines.append("```")
    lines.append("")
    lines.append("### Other: `status`, `stats`, `validate`, `logs`")
    lines.append("")

    # Key options
    lines.append("## Key options")
    lines.append("")
    lines.append("- `--data-dir DIR` — Output directory (default: `data`)")
    lines.append("- `--session` — Parliamentary session (e.g. `2024/25`) or year (e.g. `2024`)")
    lines.append("- `--since` / `--until` — Date range filter (`YYYY-MM-DD`)")
    lines.append("- `--limit N` — Max documents to collect")
    lines.append("- `--skip-content` — Metadata only (faster, no full text)")
    lines.append("- `--no-skip-existing` — Re-collect and overwrite existing documents")
    lines.append("")

    # Output format
    lines.append("## Output format")
    lines.append("")
    lines.append("```")
    lines.append("<data-dir>/<doc_type>/<session>/<doc_id>.json")
    lines.append("<data-dir>/<doc_type>/<session>/<doc_id>.md")
    lines.append("```")
    lines.append("")

    # Examples
    lines.append("## Examples")
    lines.append("")
    lines.append("```sh")
    lines.append("# Collect Supreme Court decisions from 2024")
    lines.append("juris collect domstol --type nja --session 2024")
    lines.append("")
    lines.append("# Collect government bills from session 2024/25")
    lines.append("juris collect riksdagen --type prop --session 2024/25")
    lines.append("")
    lines.append("# Collect all SOU since a date, to a custom directory")
    lines.append("juris --data-dir ./my-data collect-type sou --since 2024-01-01")
    lines.append("")
    lines.append("# Collect EU regulations (limit 10, metadata only)")
    lines.append("juris collect eur_lex --type eu_reg --limit 10 --skip-content")
    lines.append("")
    lines.append("# Collect everything (dry run to preview plan)")
    lines.append("juris collect-all --dry-run")
    lines.append("")
    lines.append("# Search collected documents")
    lines.append("juris search 'yttrandefrihet' --type prop --local-only")
    lines.append("```")

    return "\n".join(lines)


def _print_agent_help(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Eager callback for --help-agent: print reference prompt and exit."""
    if not value or ctx.resilient_parsing:
        return
    click.echo(_generate_agent_help())
    ctx.exit()


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def _format_elapsed(seconds: float) -> str:
    """Format seconds as a human-readable duration."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


@dataclasses.dataclass
class _TypeResult:
    """Tracks the outcome of collecting a single doc type."""

    doc_type: str
    source: str
    status: str = "pending"  # pending | running | done | failed
    collected: int = 0
    skipped: int = 0
    error: str | None = None


class _CollectAllTracker:
    """Tracks overall progress for a collect-all run."""

    def __init__(self, plan: list[tuple[DocType, str]]) -> None:
        self._results: dict[str, _TypeResult] = {
            dt.value: _TypeResult(doc_type=dt.value, source=src) for dt, src in plan
        }
        self._plan_order = [dt.value for dt, _ in plan]
        self._start = time.monotonic()

    def mark_started(self, doc_type: str) -> None:
        self._results[doc_type].status = "running"

    def mark_finished(self, doc_type: str, collected: int, skipped: int) -> None:
        r = self._results[doc_type]
        r.status = "done"
        r.collected = collected
        r.skipped = skipped

    def mark_failed(self, doc_type: str, error: str) -> None:
        r = self._results[doc_type]
        r.status = "failed"
        r.error = error

    def print_status_line(self) -> None:
        done = sum(1 for r in self._results.values() if r.status in ("done", "failed"))
        total_c = sum(r.collected for r in self._results.values())
        total_s = sum(r.skipped for r in self._results.values())
        failed = sum(1 for r in self._results.values() if r.status == "failed")
        elapsed = _format_elapsed(time.monotonic() - self._start)
        parts = [
            f"[{done}/{len(self._results)} types done]",
            f"{elapsed} elapsed",
            f"{total_c} saved, {total_s} skipped",
        ]
        if failed:
            parts.append(f"{failed} failed")
        click.echo("  " + " | ".join(parts))

    def elapsed(self) -> str:
        return _format_elapsed(time.monotonic() - self._start)

    @property
    def results(self) -> dict[str, _TypeResult]:
        return self._results


class _ProgressTracker:
    """CLI progress reporter that implements :class:`ProgressCallback`."""

    def __init__(self, label: str, total: int | None = None) -> None:
        self.label = label
        self.total = total
        self._collected = 0
        self._skipped = 0
        self._last_line_len = 0

    # -- ProgressCallback protocol ------------------------------------------

    def on_save(self, doc_id: str, path: Path) -> None:
        self._collected += 1
        self._render()

    def on_skip(self, doc_id: str) -> None:
        self._skipped += 1
        self._render()

    def on_finish(self) -> None:
        click.echo()  # newline after progress

    # -- internal -----------------------------------------------------------

    def _render(self) -> None:
        collected, skipped = self._collected, self._skipped
        current = collected + skipped
        if self.total:
            pct = min(100, int(current / self.total * 100))
            bar_width = 20
            filled = int(bar_width * pct / 100)
            bar = "█" * filled + "░" * (bar_width - filled)
            line = f"\r  {self.label}: {bar} {pct}% ({collected} saved, {skipped} skipped)"
        else:
            line = f"\r  {self.label}: {collected} saved, {skipped} skipped"
        padded = line.ljust(self._last_line_len)
        self._last_line_len = len(line)
        click.echo(padded, nl=False)


class _VerboseReporter:
    """Line-per-document reporter that implements :class:`ProgressCallback`."""

    def on_save(self, doc_id: str, path: Path) -> None:
        click.echo(f"  saved {doc_id} -> {path}")

    def on_skip(self, doc_id: str) -> None:
        click.echo(f"  skip {doc_id} (exists)")

    def on_finish(self) -> None:
        pass


@click.group()
@click.option(
    "--help-agent",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_print_agent_help,
    help="Print a reference prompt for AI agents and exit.",
)
@click.option(
    "--data-dir",
    type=click.Path(),
    default="data",
    help="Output directory for collected data.",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging.")
@click.pass_context
def main(ctx: click.Context, data_dir: str, verbose: bool) -> None:
    """juris — Swedish legal data collection tool."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    ctx.ensure_object(dict)
    ctx.obj["data_dir"] = Path(data_dir)


@main.command()
@click.argument("source", type=click.Choice(_COLLECTOR_NAMES))
@click.option(
    "--type",
    "doc_type",
    required=True,
    type=click.Choice([dt.value for dt in DocType]),
    help="Document type to collect.",
)
@click.option("--session", default=None, help="Parliamentary session, e.g. 2024/25.")
@click.option("--since", default=None, help="Collect documents from this date (YYYY-MM-DD).")
@click.option("--until", default=None, help="Collect documents until this date (YYYY-MM-DD).")
@click.option("--limit", default=None, type=int, help="Maximum number of documents to collect.")
@click.option(
    "--skip-existing/--no-skip-existing",
    default=True,
    help="Skip already collected documents.",
)
@click.option(
    "--skip-content/--no-skip-content",
    default=False,
    help="Skip fetching full text (faster, metadata only).",
)
@click.pass_context
def collect(
    ctx: click.Context,
    source: str,
    doc_type: str,
    session: str | None,
    since: str | None,
    until: str | None,
    limit: int | None,
    skip_existing: bool,
    skip_content: bool,
) -> None:
    """Collect documents from a source."""
    data_dir: Path = ctx.obj["data_dir"]
    dt = DocType(doc_type)

    collector_cls = get_collector_class(source)
    if dt not in collector_cls.supported_doc_types:
        supported = ", ".join(t.value for t in collector_cls.supported_doc_types)
        raise click.UsageError(
            f"Source '{source}' does not support type '{doc_type}'. Supported types: {supported}"
        )

    async def _run() -> None:
        logs = log_dir_path(data_dir)
        collection_logger = CollectionLogger(logs, source, dt.value)
        file_handler = setup_file_logging(logs, source, dt.value)
        progress = CompositeProgress(_VerboseReporter(), collection_logger)
        try:
            collected, skipped = await collect_from_source(
                source,
                dt,
                data_dir,
                session=session,
                since=_parse_date(since),
                until=_parse_date(until),
                limit=limit,
                skip_existing=skip_existing,
                skip_content=skip_content,
                progress=progress,
            )
            click.echo(f"\nDone: {collected} collected, {skipped} skipped")
        finally:
            logging.getLogger().removeHandler(file_handler)
            file_handler.close()

    click.echo(f"Collecting {dt.value} from {source}...")
    asyncio.run(_run())


@main.command("collect-type")
@click.argument("doc_type", type=click.Choice([dt.value for dt in DocType]))
@click.option("--session", default=None, help="Parliamentary session, e.g. 2024/25.")
@click.option("--since", default=None, help="Collect documents from this date (YYYY-MM-DD).")
@click.option("--until", default=None, help="Collect documents until this date (YYYY-MM-DD).")
@click.option("--limit", default=None, type=int, help="Max documents per provider.")
@click.option(
    "--skip-existing/--no-skip-existing",
    default=True,
    help="Skip already collected documents.",
)
@click.option(
    "--skip-content/--no-skip-content",
    default=False,
    help="Skip fetching full text (faster, metadata only).",
)
@click.option("--dry-run", is_flag=True, help="Show which providers would be used, then exit.")
@click.option(
    "--all-providers",
    is_flag=True,
    help="Use all providers instead of only the preferred one.",
)
@click.pass_context
def collect_type(
    ctx: click.Context,
    doc_type: str,
    session: str | None,
    since: str | None,
    until: str | None,
    limit: int | None,
    skip_existing: bool,
    skip_content: bool,
    dry_run: bool,
    all_providers: bool,
) -> None:
    """Collect a document type using the best provider.

    By default only the preferred (highest quality) provider is used.
    Pass --all-providers to collect from every provider that supports the type.
    """
    data_dir: Path = ctx.obj["data_dir"]
    dt = DocType(doc_type)

    doc_type_providers = get_doc_type_providers()
    preferred_providers = get_preferred_providers()

    if all_providers:
        providers = doc_type_providers.get(doc_type, [])
    else:
        preferred = preferred_providers.get(doc_type)
        providers = [preferred] if preferred else []

    if not providers:
        raise click.UsageError(f"No providers found for document type '{doc_type}'.")

    all_available = doc_type_providers.get(doc_type, [])
    skipped = [p for p in all_available if p not in providers]

    if dry_run:
        click.echo(f"Providers for '{doc_type}': {', '.join(providers)}")
        if skipped:
            click.echo(f"Skipped (lower quality): {', '.join(skipped)}")
        return

    click.echo(f"Collecting {doc_type} from {len(providers)} provider(s): {', '.join(providers)}")
    if skipped:
        click.echo(f"  (skipped: {', '.join(skipped)} — use --all-providers to include)")

    async def _run_all() -> tuple[int, int]:
        grand_collected = 0
        grand_skipped = 0
        logs = log_dir_path(data_dir)

        for i, source_name in enumerate(providers, 1):
            click.echo(f"\n[{i}/{len(providers)}] {source_name}")
            collection_logger = CollectionLogger(logs, source_name, dt.value)
            file_handler = setup_file_logging(logs, source_name, dt.value)
            tracker = _ProgressTracker(
                f"{source_name}/{dt.value}",
                total=limit,
            )
            progress = CompositeProgress(tracker, collection_logger)
            try:
                collected, skipped_count = await collect_from_source(
                    source_name,
                    dt,
                    data_dir,
                    session=session,
                    since=_parse_date(since),
                    until=_parse_date(until),
                    limit=limit,
                    skip_existing=skip_existing,
                    skip_content=skip_content,
                    progress=progress,
                )
                click.echo(f"  {source_name}: {collected} collected, {skipped_count} skipped")
                grand_collected += collected
                grand_skipped += skipped_count
            finally:
                logging.getLogger().removeHandler(file_handler)
                file_handler.close()

        return grand_collected, grand_skipped

    total_collected, total_skipped = asyncio.run(_run_all())
    click.echo(
        f"\nTotal: {total_collected} collected, {total_skipped} skipped "
        f"across {len(providers)} provider(s)"
    )


@main.command("collect-all")
@click.option("--since", default=None, help="Collect documents from this date (YYYY-MM-DD).")
@click.option("--until", default=None, help="Collect documents until this date (YYYY-MM-DD).")
@click.option("--limit", default=None, type=int, help="Max documents per doc type.")
@click.option(
    "--skip-existing/--no-skip-existing",
    default=True,
    help="Skip already collected documents.",
)
@click.option(
    "--skip-content/--no-skip-content",
    default=False,
    help="Skip fetching full text (faster, metadata only).",
)
@click.option("--dry-run", is_flag=True, help="Show the plan, then exit.")
@click.option(
    "--concurrent/--sequential",
    default=False,
    help="Run independent sources concurrently (faster, but noisier output).",
)
@click.option(
    "--max-concurrency",
    default=4,
    type=int,
    help="Maximum number of concurrent source collections (default 4).",
)
@click.pass_context
def collect_all(
    ctx: click.Context,
    since: str | None,
    until: str | None,
    limit: int | None,
    skip_existing: bool,
    skip_content: bool,
    dry_run: bool,
    concurrent: bool,
    max_concurrency: int,
) -> None:
    """Collect all document types from all providers (best source per type).

    When multiple providers support the same document type, only the
    best provider is used.  Selection prefers structured APIs over web
    scraping for reliability and speed.

    Use --concurrent to run independent sources in parallel for faster
    collection. Sources sharing the same provider are grouped and run
    sequentially within each group to respect rate limits.

    \b
    Preferred providers for overlapping types:
      prop, sou, dir, skr  ->  riksdagen  (JSON API, faster, reliable)
      ds, lagr             ->  regeringen (sole provider)
    """
    data_dir: Path = ctx.obj["data_dir"]

    preferred_providers = get_preferred_providers()
    doc_type_providers = get_doc_type_providers()

    # Build the plan: list of (doc_type, source_name) pairs
    plan: list[tuple[DocType, str]] = []
    for dt in DocType:
        source_name = preferred_providers.get(dt.value)
        if source_name:
            plan.append((dt, source_name))
        else:
            logger.warning("No preferred provider for %s, skipping", dt.value)

    if dry_run:
        click.echo("Collection plan (best provider per document type):\n")
        for dt, source_name in plan:
            providers = doc_type_providers.get(dt.value, [])
            alt = [p for p in providers if p != source_name]
            alt_str = f"  (skipped: {', '.join(alt)})" if alt else ""
            click.echo(f"  {dt.value:12s} <- {source_name}{alt_str}")
        click.echo(f"\n{len(plan)} document types across {len({s for _, s in plan})} providers")
        if concurrent:
            click.echo(f"Mode: concurrent (max {max_concurrency} parallel tasks)")
        else:
            click.echo("Mode: sequential")
        return

    tracker = _CollectAllTracker(plan)

    click.echo(f"Collecting {len(plan)} document types from {len({s for _, s in plan})} providers")

    if concurrent:
        click.echo(f"Mode: concurrent (max {max_concurrency} parallel tasks)")

        async def _run_concurrent() -> None:
            source_groups: dict[str, list[DocType]] = {}
            for dt, source_name in plan:
                source_groups.setdefault(source_name, []).append(dt)

            semaphore = asyncio.Semaphore(max_concurrency)
            logs = log_dir_path(data_dir)

            async def _collect_group(source_name: str, doc_types: list[DocType]) -> None:
                async with semaphore:
                    for dt in doc_types:
                        tracker.mark_started(dt.value)
                        click.echo(f"  Starting {dt.value} <- {source_name}")
                        collection_logger = CollectionLogger(logs, source_name, dt.value)
                        file_handler = setup_file_logging(logs, source_name, dt.value)
                        progress_bar = _ProgressTracker(
                            f"{source_name}/{dt.value}",
                            total=limit,
                        )
                        progress = CompositeProgress(progress_bar, collection_logger)
                        try:
                            collected, skipped = await collect_from_source(
                                source_name,
                                dt,
                                data_dir,
                                since=_parse_date(since),
                                until=_parse_date(until),
                                limit=limit,
                                skip_existing=skip_existing,
                                skip_content=skip_content,
                                progress=progress,
                            )
                            tracker.mark_finished(dt.value, collected, skipped)
                        except Exception as exc:
                            tracker.mark_failed(dt.value, str(exc))
                            click.echo(f"  ERROR {dt.value}: {exc}", err=True)
                        finally:
                            logging.getLogger().removeHandler(file_handler)
                            file_handler.close()
                        tracker.print_status_line()

            tasks = [
                _collect_group(source_name, doc_types)
                for source_name, doc_types in source_groups.items()
            ]
            await asyncio.gather(*tasks)

        asyncio.run(_run_concurrent())
    else:

        async def _run_sequential() -> None:
            logs = log_dir_path(data_dir)

            for i, (dt, source_name) in enumerate(plan, 1):
                tracker.mark_started(dt.value)
                click.echo(f"\n[{i}/{len(plan)}] {dt.value} <- {source_name}")
                collection_logger = CollectionLogger(logs, source_name, dt.value)
                file_handler = setup_file_logging(logs, source_name, dt.value)
                progress_bar = _ProgressTracker(
                    f"{source_name}/{dt.value}",
                    total=limit,
                )
                progress = CompositeProgress(progress_bar, collection_logger)
                try:
                    collected, skipped = await collect_from_source(
                        source_name,
                        dt,
                        data_dir,
                        since=_parse_date(since),
                        until=_parse_date(until),
                        limit=limit,
                        skip_existing=skip_existing,
                        skip_content=skip_content,
                        progress=progress,
                    )
                    tracker.mark_finished(dt.value, collected, skipped)
                except Exception as exc:
                    tracker.mark_failed(dt.value, str(exc))
                    click.echo(f"  ERROR {dt.value}: {exc}", err=True)
                finally:
                    logging.getLogger().removeHandler(file_handler)
                    file_handler.close()
                tracker.print_status_line()

        asyncio.run(_run_sequential())

    # Print summary
    total_c = sum(r.collected for r in tracker.results.values())
    total_s = sum(r.skipped for r in tracker.results.values())
    failed_types = [r for r in tracker.results.values() if r.status == "failed"]
    click.echo(
        f"\nCollection complete in {tracker.elapsed()}: "
        f"{total_c} collected, {total_s} skipped "
        f"across {len(plan)} document types"
    )
    if failed_types:
        click.echo("\nFailures:")
        for r in failed_types:
            click.echo(f"  {r.doc_type} ({r.source}): {r.error}")

    # Auto-generate a report
    from juris.report import generate_report, save_report

    rpt = generate_report(data_dir)
    report_path = save_report(rpt, data_dir)
    click.echo(
        f"\nReport: {rpt.total_documents} documents across "
        f"{rpt.total_doc_types} types (saved to {report_path})"
    )


# ---------------------------------------------------------------------------
# report command group
# ---------------------------------------------------------------------------


def _display_report(rpt: CollectionReport) -> None:
    """Print a human-readable report to the terminal."""
    click.echo(f"Collection Report ({rpt.generated_at})")
    click.echo(f"Total: {rpt.total_documents:,} documents across {rpt.total_doc_types} doc types\n")

    hdr = f"  {'Type':<14s} {'Source':<12s} {'On disk':>8s}  {'Date range':<23s} {'Last run':<12s}"
    click.echo(hdr)
    click.echo(f"  {'─' * 73}")

    empty_types: list[str] = []
    for s in rpt.doc_types:
        if s.date_min and s.date_max:
            dr = f"{s.date_min} – {s.date_max}"
        else:
            dr = "—"
        last_run = s.last_run_at[:10] if s.last_run_at else "—"
        mark = "  <- empty" if s.on_disk == 0 else ""
        click.echo(
            f"  {s.doc_type:<14s} {s.source:<12s} {s.on_disk:>8,}  {dr:<23s} {last_run:<12s}{mark}"
        )
        if s.on_disk == 0:
            empty_types.append(s.doc_type)

    click.echo(f"  {'─' * 73}")
    click.echo(f"  {'Total':<14s} {'':12s} {rpt.total_documents:>8,}")

    # Coverage by year
    has_coverage = any(s.by_year for s in rpt.doc_types)
    if has_coverage:
        click.echo("\nCoverage by year:")
        for s in rpt.doc_types:
            if not s.by_year:
                click.echo(f"  {s.doc_type}: (none)")
                continue
            click.echo(f"  {s.doc_type} ({s.on_disk:,} docs):")
            parts: list[str] = []
            for yr in sorted(s.by_year):
                cnt = s.by_year[yr]
                pct = s.by_year_pct.get(yr, 0.0)
                parts.append(f"{yr}: {cnt:>4} ({pct:.1f}%)")
            # Print in rows of 5 entries
            for i in range(0, len(parts), 5):
                chunk = "  ".join(parts[i : i + 5])
                click.echo(f"    {chunk}")

    if empty_types:
        click.echo(f"\nGaps (no documents on disk): {', '.join(empty_types)}")


def _display_diff(diff: ReportDiff) -> None:
    """Print a human-readable diff between two reports."""
    click.echo(
        f"Comparing {diff.before_id[:8]} "
        f"({diff.before_generated_at[:10]}) → current "
        f"({diff.after_generated_at[:10]}):\n"
    )
    hdr = f"  {'Type':<14s} {'Before':>8s}  {'After':>8s}  {'Delta':>8s}"
    click.echo(hdr)
    click.echo(f"  {'─' * 42}")

    for d in diff.doc_types:
        sign = "+" if d.delta > 0 else ""
        click.echo(
            f"  {d.doc_type:<14s} {d.on_disk_before:>8,}"
            f"  {d.on_disk_after:>8,}  {sign}{d.delta:>7,}"
        )

    click.echo(f"  {'─' * 42}")
    sign = "+" if diff.total_delta > 0 else ""
    click.echo(
        f"  {'Total':<14s} {diff.total_before:>8,}"
        f"  {diff.total_after:>8,}  {sign}{diff.total_delta:>7,}"
    )


@main.group(invoke_without_command=True)
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON to stdout.")
@click.pass_context
def report(ctx: click.Context, output_json: bool) -> None:
    """Generate or view collection coverage reports."""
    ctx.ensure_object(dict)
    ctx.obj["output_json"] = output_json
    if ctx.invoked_subcommand is not None:
        return
    # Default: generate a new report
    data_dir: Path = ctx.obj["data_dir"]

    from juris.report import generate_report, save_report

    rpt = generate_report(data_dir)
    save_report(rpt, data_dir)

    if output_json:
        click.echo(json.dumps(rpt.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        _display_report(rpt)


@report.command("list")
@click.pass_context
def report_list(ctx: click.Context) -> None:
    """List historical reports."""
    data_dir: Path = ctx.obj["data_dir"]

    from juris.report import list_reports

    entries = list_reports(data_dir)
    if not entries:
        click.echo("No reports found. Run 'juris report' to generate one.")
        return

    click.echo(f"  {'ID':<10s} {'Generated':18s} {'Documents':>10s}")
    click.echo(f"  {'─' * 40}")
    for e in entries:
        click.echo(f"  {e.id[:8]:<10s} {e.generated_at[:16]:18s} {e.total_documents:>10,}")


@report.command("show")
@click.argument("report_id")
@click.pass_context
def report_show(ctx: click.Context, report_id: str) -> None:
    """Display a specific historical report."""
    data_dir: Path = ctx.obj["data_dir"]
    output_json: bool = ctx.obj.get("output_json", False)

    from juris.report import load_report

    rpt = load_report(report_id, data_dir)
    if not rpt:
        raise click.UsageError(f"Report '{report_id}' not found (or ambiguous prefix).")

    if output_json:
        click.echo(json.dumps(rpt.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        _display_report(rpt)


@report.command("diff")
@click.argument("report_id")
@click.pass_context
def report_diff(ctx: click.Context, report_id: str) -> None:
    """Compare current state to a historical report."""
    data_dir: Path = ctx.obj["data_dir"]

    from juris.report import diff_reports, generate_report, load_report

    old = load_report(report_id, data_dir)
    if not old:
        raise click.UsageError(f"Report '{report_id}' not found (or ambiguous prefix).")

    current = generate_report(data_dir)
    result = diff_reports(old, current)
    _display_diff(result)


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show collection state for all sources and document types."""
    data_dir: Path = ctx.obj["data_dir"]
    state_dir = data_dir / ".state"

    if not state_dir.exists():
        click.echo("No collection state found. Run 'juris collect' first.")
        return

    for state_file in sorted(state_dir.glob("*.json")):
        data = json.loads(state_file.read_text(encoding="utf-8"))
        src = data.get("source", "?")
        dt = data.get("doc_type", "?")
        total = data.get("total_collected", 0)
        last_date = data.get("last_fetched_date", "—")
        last_run = data.get("last_run_at", "—")
        click.echo(f"  {src}/{dt}: {total} docs, latest={last_date}, last_run={last_run}")


@main.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Count collected documents per type."""
    data_dir: Path = ctx.obj["data_dir"]

    if not data_dir.exists():
        click.echo("No data directory found.")
        return

    total = 0
    for dt in DocType:
        type_dir = data_dir / dt.value
        if not type_dir.exists():
            continue
        count = len(list(type_dir.rglob("*.json")))
        if count:
            click.echo(f"  {dt.value}: {count}")
            total += count

    click.echo(f"  total: {total}")


@main.command()
@click.argument("query")
@click.option(
    "--source",
    type=click.Choice(_COLLECTOR_NAMES),
    default=None,
    help="Search only this source.",
)
@click.option(
    "--type",
    "doc_type",
    type=click.Choice([dt.value for dt in DocType]),
    default=None,
    help="Filter by document type.",
)
@click.option("--local-only", is_flag=True, help="Search only collected documents on disk.")
@click.option("--provider-only", is_flag=True, help="Search only via provider APIs.")
@click.option("--limit", default=20, type=int, help="Maximum results to display.")
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    source: str | None,
    doc_type: str | None,
    local_only: bool,
    provider_only: bool,
    limit: int,
) -> None:
    """Search for documents by keyword.

    Searches both collected local documents and provider APIs (where supported).
    Use --local-only to search only what has been collected, or --provider-only
    to search only via remote APIs.

    \b
    Providers with search support: jo_jk (JK only), hudoc
    """
    data_dir: Path = ctx.obj["data_dir"]
    dt = DocType(doc_type) if doc_type else None
    src = Source(source) if source else None

    if local_only and provider_only:
        raise click.UsageError("Cannot use both --local-only and --provider-only.")

    searchable = get_searchable_sources()

    if not local_only:
        if source and source not in searchable:
            click.echo(
                f"Note: '{source}' does not support remote search. Searching local documents only."
            )
            local_only = True

    async def _run() -> list[SearchResult]:
        from juris.search import search_all

        return await search_all(
            query,
            data_dir,
            doc_type=dt,
            source=src,
            local_only=local_only,
            provider_only=provider_only,
            limit=limit,
        )

    results = asyncio.run(_run())
    _display_search_results(results, query)


def _display_search_results(results: list[SearchResult], query: str) -> None:
    """Format and display search results in the terminal."""
    if not results:
        click.echo("No results found.")
        return

    click.echo(f"\n  {len(results)} result(s) for '{query}':\n")

    for i, r in enumerate(results, 1):
        if r.local:
            local_marker = click.style("LOCAL", fg="green")
        else:
            local_marker = click.style("REMOTE", fg="yellow")
        date_str = str(r.date) if r.date else "—"
        type_str = r.doc_type.value.upper()

        click.echo(f"  {i:3d}. [{local_marker}] [{type_str}] {r.title}")
        click.echo(f"       {r.designation or '—'}  |  {date_str}  |  {r.source.value}")
        if r.snippet:
            click.echo(f"       {r.snippet}")
        if r.source_url:
            click.echo(f"       {r.source_url}")
        click.echo()


@main.command()
@click.option(
    "--type",
    "doc_type",
    default=None,
    type=click.Choice([dt.value for dt in DocType]),
    help="Only validate this document type.",
)
@click.option("--fix", is_flag=True, help="Attempt to auto-fix minor issues (e.g. missing doc_id).")
@click.pass_context
def validate(ctx: click.Context, doc_type: str | None, fix: bool) -> None:
    """Validate collected data quality.

    Checks for missing required fields, suspicious values, duplicate doc_ids,
    and other data quality issues across all collected documents.
    """
    data_dir: Path = ctx.obj["data_dir"]

    if not data_dir.exists():
        click.echo("No data directory found.")
        return

    types_to_check = [DocType(doc_type)] if doc_type else list(DocType)

    total_docs = 0
    total_warnings = 0
    total_errors = 0
    seen_doc_ids: dict[str, str] = {}  # doc_id -> file path

    for dt in types_to_check:
        type_dir = data_dir / dt.value
        if not type_dir.exists():
            continue

        json_files = list(type_dir.rglob("*.json"))
        if not json_files:
            continue

        for json_path in sorted(json_files):
            total_docs += 1
            rel_path = str(json_path.relative_to(data_dir))
            issues: list[tuple[str, str]] = []  # (level, message)

            try:
                raw = json.loads(json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                issues.append(("ERROR", f"Cannot read file: {e}"))
                total_errors += 1
                _print_issues(rel_path, issues)
                continue

            # Required fields check
            for field in ("doc_id", "doc_type", "designation", "title", "date", "source"):
                val = raw.get(field)
                if not val:
                    issues.append(("ERROR", f"Missing required field: {field}"))
                    total_errors += 1

            # Duplicate doc_id check
            doc_id = raw.get("doc_id", "")
            if doc_id:
                if doc_id in seen_doc_ids:
                    issues.append(("WARN", f"Duplicate doc_id (also in {seen_doc_ids[doc_id]})"))
                    total_warnings += 1
                else:
                    seen_doc_ids[doc_id] = rel_path

            # Suspicious designation
            designation = raw.get("designation", "")
            if designation and len(designation) > 100:
                issues.append(("WARN", f"Suspiciously long designation ({len(designation)} chars)"))
                total_warnings += 1
            if designation and designation == raw.get("title", ""):
                issues.append(("WARN", "Designation equals title (likely fallback)"))
                total_warnings += 1

            # Title quality
            title = raw.get("title", "")
            if title and len(title) < 5:
                issues.append(("WARN", f"Very short title: '{title}'"))
                total_warnings += 1

            # Missing content
            if not raw.get("text") and not raw.get("html") and not raw.get("summary"):
                issues.append(("WARN", "No text, html, or summary content"))
                total_warnings += 1

            # Date sanity
            date_str = raw.get("date", "")
            if date_str:
                try:
                    from datetime import date as date_cls

                    doc_date = date_cls.fromisoformat(date_str)
                    if doc_date.year < 1900:
                        issues.append(("WARN", f"Suspiciously old date: {date_str}"))
                        total_warnings += 1
                    if doc_date > date_cls.today():
                        issues.append(("WARN", f"Future date: {date_str}"))
                        total_warnings += 1
                except ValueError:
                    issues.append(("ERROR", f"Invalid date format: {date_str}"))
                    total_errors += 1

            # Session consistency
            session = raw.get("session")
            if session and date_str:
                try:
                    year = int(session[:4])
                    doc_year = int(date_str[:4])
                    if abs(year - doc_year) > 2:
                        issues.append(
                            (
                                "WARN",
                                f"Session {session} doesn't match date year {doc_year}",
                            )
                        )
                        total_warnings += 1
                except (ValueError, IndexError):
                    pass

            # Attachments check
            for i, att in enumerate(raw.get("attachments", [])):
                if not att.get("url"):
                    issues.append(("WARN", f"Attachment {i} missing URL"))
                    total_warnings += 1
                if not att.get("filename"):
                    issues.append(("WARN", f"Attachment {i} missing filename"))
                    total_warnings += 1

            if issues:
                _print_issues(rel_path, issues)

    click.echo(f"\nValidation complete: {total_docs} documents checked")
    click.echo(f"  {total_errors} errors, {total_warnings} warnings")
    if total_errors == 0 and total_warnings == 0:
        click.echo("  All documents passed validation!")


def _print_issues(path: str, issues: list[tuple[str, str]]) -> None:
    """Print validation issues for a document."""
    click.echo(f"\n  {path}:")
    for level, message in issues:
        marker = click.style(level, fg="red" if level == "ERROR" else "yellow")
        click.echo(f"    [{marker}] {message}")


@main.command()
@click.option(
    "--source",
    type=click.Choice(_COLLECTOR_NAMES),
    default=None,
    help="Filter by source.",
)
@click.option(
    "--type",
    "doc_type",
    type=click.Choice([dt.value for dt in DocType]),
    default=None,
    help="Filter by document type.",
)
@click.option("--failures", is_flag=True, help="Show only failed or warned documents.")
@click.option("--run", "run_name", default=None, help="Show entries from a specific run file.")
@click.pass_context
def logs(
    ctx: click.Context,
    source: str | None,
    doc_type: str | None,
    failures: bool,
    run_name: str | None,
) -> None:
    """View collection run logs.

    Lists recent runs with summaries.  Use --failures to see only documents
    that failed or had warnings.  Use --run to inspect a specific run file.
    """
    data_dir: Path = ctx.obj["data_dir"]
    logs_dir = data_dir / ".logs"

    if not logs_dir.exists():
        click.echo("No logs found. Run a collection command first.")
        return

    jsonl_files = sorted(logs_dir.glob("*.jsonl"), reverse=True)
    if not jsonl_files:
        click.echo("No log files found.")
        return

    # Filter by source/doc_type from filename ({ts}_{source}_{doctype}.jsonl)
    if source or doc_type:
        filtered: list[Path] = []
        for f in jsonl_files:
            parts = f.stem.split("_", 1)
            if len(parts) < 2:
                continue
            name_part = parts[1]  # e.g. "riksdagen_prop"
            if source and source not in name_part:
                continue
            if doc_type and not name_part.endswith(doc_type):
                continue
            filtered.append(f)
        jsonl_files = filtered

    # Show a specific run
    if run_name:
        matches = [f for f in jsonl_files if run_name in f.stem]
        if not matches:
            click.echo(f"No log file matching '{run_name}'.")
            return
        _display_run(matches[0], failures)
        return

    # List recent runs with summaries
    click.echo(f"  {'Run':55s}  {'Saved':>6s}  {'Skip':>6s}  {'Fail':>6s}  {'Warn':>6s}")
    click.echo(f"  {'─' * 55}  {'─' * 6}  {'─' * 6}  {'─' * 6}  {'─' * 6}")
    for f in jsonl_files[:20]:
        summary = _read_run_summary(f)
        if summary:
            click.echo(
                f"  {f.stem:55s}  {summary['collected']:6d}"
                f"  {summary['skipped']:6d}  {summary['failed']:6d}"
                f"  {summary['warnings']:6d}"
            )
        else:
            click.echo(f"  {f.stem:55s}  (no summary)")

    if len(jsonl_files) > 20:
        click.echo(f"\n  ... and {len(jsonl_files) - 20} more (use --source/--type to filter)")


def _read_run_summary(path: Path) -> dict[str, int] | None:
    """Read the summary line (last line) from a JSONL log file."""
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return None
    try:
        last = json.loads(lines[-1])
        if last.get("type") == "summary":
            return {
                "collected": last.get("total_collected", 0),
                "skipped": last.get("total_skipped", 0),
                "failed": last.get("total_failed", 0),
                "warnings": last.get("total_warnings", 0),
            }
    except json.JSONDecodeError:
        pass
    return None


def _display_run(path: Path, failures_only: bool) -> None:
    """Display entries from a single run JSONL file."""
    click.echo(f"  Run: {path.stem}\n")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    entry_count = 0

    for line in lines:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        if data.get("type") == "summary":
            click.echo(
                f"\n  Summary: {data.get('total_collected', 0)} collected, "
                f"{data.get('total_skipped', 0)} skipped, "
                f"{data.get('total_failed', 0)} failed, "
                f"{data.get('total_warnings', 0)} warnings"
            )
            click.echo(f"  Period: {data.get('started_at', '?')} -> {data.get('finished_at', '?')}")
            continue

        status = data.get("status", "?")
        if failures_only and status in ("ok", "skipped"):
            continue

        entry_count += 1
        status_color = {
            "ok": "green",
            "ok_with_warnings": "yellow",
            "skipped": "cyan",
            "failed": "red",
        }.get(status, None)
        status_str = click.style(status, fg=status_color) if status_color else status

        click.echo(f"  {data.get('doc_id', '?'):40s}  [{status_str}]")
        for w in data.get("warnings", []):
            click.echo(f"    WARNING: {w}")
        if data.get("error"):
            click.echo(f"    ERROR: {data['error']}")

    if entry_count == 0 and failures_only:
        click.echo("  No failures or warnings found.")


@main.command()
@click.argument("command", default="juris")
def man(command: str) -> None:
    """Display manual pages for juris commands."""
    man_dir = Path(__file__).resolve().parent.parent.parent / "man"
    page = man_dir / f"{command}.md"
    if not page.exists():
        available = sorted(p.stem for p in man_dir.glob("*.md"))
        raise click.UsageError(f"No manual page for '{command}'. Available: {', '.join(available)}")
    click.echo(page.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
