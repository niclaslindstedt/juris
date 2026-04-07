"""CLI entry point for juris."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from pathlib import Path

import click

from juris.collectors import (
    get_collector_class,
    get_doc_type_providers,
    get_preferred_providers,
    get_registry,
)
from juris.models import DocType
from juris.pipeline import collect_from_source

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path("data")

# Resolved at import time (auto-discovery has already run).
_COLLECTOR_NAMES = sorted(get_registry().keys())


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


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
            line = (
                f"\r  {self.label}: {bar} {pct}% "
                f"({collected} saved, {skipped} skipped)"
            )
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
    "--data-dir", type=click.Path(), default="data",
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
    "--type", "doc_type", required=True,
    type=click.Choice([dt.value for dt in DocType]),
    help="Document type to collect.",
)
@click.option("--session", default=None, help="Parliamentary session, e.g. 2024/25.")
@click.option("--since", default=None, help="Collect documents from this date (YYYY-MM-DD).")
@click.option("--until", default=None, help="Collect documents until this date (YYYY-MM-DD).")
@click.option("--limit", default=None, type=int, help="Maximum number of documents to collect.")
@click.option(
    "--skip-existing/--no-skip-existing", default=True,
    help="Skip already collected documents.",
)
@click.option(
    "--skip-content/--no-skip-content", default=False,
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
            f"Source '{source}' does not support type '{doc_type}'. "
            f"Supported types: {supported}"
        )

    async def _run() -> None:
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
            progress=_VerboseReporter(),
        )
        click.echo(f"\nDone: {collected} collected, {skipped} skipped")

    click.echo(f"Collecting {dt.value} from {source}...")
    asyncio.run(_run())


@main.command("collect-type")
@click.argument("doc_type", type=click.Choice([dt.value for dt in DocType]))
@click.option("--session", default=None, help="Parliamentary session, e.g. 2024/25.")
@click.option("--since", default=None, help="Collect documents from this date (YYYY-MM-DD).")
@click.option("--until", default=None, help="Collect documents until this date (YYYY-MM-DD).")
@click.option("--limit", default=None, type=int, help="Max documents per provider.")
@click.option(
    "--skip-existing/--no-skip-existing", default=True,
    help="Skip already collected documents.",
)
@click.option(
    "--skip-content/--no-skip-content", default=False,
    help="Skip fetching full text (faster, metadata only).",
)
@click.option("--dry-run", is_flag=True, help="Show which providers would be used, then exit.")
@click.option(
    "--all-providers", is_flag=True,
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

    click.echo(
        f"Collecting {doc_type} from {len(providers)} provider(s): "
        f"{', '.join(providers)}"
    )
    if skipped:
        click.echo(f"  (skipped: {', '.join(skipped)} — use --all-providers to include)")

    async def _run_all() -> tuple[int, int]:
        grand_collected = 0
        grand_skipped = 0

        for i, source_name in enumerate(providers, 1):
            click.echo(f"\n[{i}/{len(providers)}] {source_name}")
            tracker = _ProgressTracker(
                f"{source_name}/{dt.value}", total=limit,
            )
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
                progress=tracker,
            )
            click.echo(f"  {source_name}: {collected} collected, {skipped_count} skipped")
            grand_collected += collected
            grand_skipped += skipped_count

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
    "--skip-existing/--no-skip-existing", default=True,
    help="Skip already collected documents.",
)
@click.option(
    "--skip-content/--no-skip-content", default=False,
    help="Skip fetching full text (faster, metadata only).",
)
@click.option("--dry-run", is_flag=True, help="Show the plan, then exit.")
@click.option(
    "--concurrent/--sequential", default=False,
    help="Run independent sources concurrently (faster, but noisier output).",
)
@click.option(
    "--max-concurrency", default=4, type=int,
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
        click.echo(f"\n{len(plan)} document types across "
                    f"{len({s for _, s in plan})} providers")
        if concurrent:
            click.echo(f"Mode: concurrent (max {max_concurrency} parallel tasks)")
        else:
            click.echo("Mode: sequential")
        return

    click.echo(
        f"Collecting {len(plan)} document types from "
        f"{len({s for _, s in plan})} providers"
    )

    if concurrent:
        click.echo(f"Mode: concurrent (max {max_concurrency} parallel tasks)")

        async def _run_concurrent() -> tuple[int, int]:
            # Group by source to avoid hammering the same API concurrently
            source_groups: dict[str, list[DocType]] = {}
            for dt, source_name in plan:
                source_groups.setdefault(source_name, []).append(dt)

            semaphore = asyncio.Semaphore(max_concurrency)

            async def _collect_group(
                source_name: str, doc_types: list[DocType]
            ) -> tuple[int, int]:
                """Collect all doc types for a single source sequentially."""
                group_collected = 0
                group_skipped = 0
                async with semaphore:
                    for dt in doc_types:
                        click.echo(f"  Starting {dt.value} <- {source_name}")
                        tracker = _ProgressTracker(
                            f"{source_name}/{dt.value}", total=limit,
                        )
                        collected, skipped = await collect_from_source(
                            source_name,
                            dt,
                            data_dir,
                            since=_parse_date(since),
                            until=_parse_date(until),
                            limit=limit,
                            skip_existing=skip_existing,
                            skip_content=skip_content,
                            progress=tracker,
                        )
                        click.echo(
                            f"  Done {source_name}/{dt.value}: "
                            f"{collected} collected, {skipped} skipped"
                        )
                        group_collected += collected
                        group_skipped += skipped
                return group_collected, group_skipped

            tasks = [
                _collect_group(source_name, doc_types)
                for source_name, doc_types in source_groups.items()
            ]
            results = await asyncio.gather(*tasks)

            grand_collected = sum(c for c, _ in results)
            grand_skipped = sum(s for _, s in results)
            return grand_collected, grand_skipped

        total_collected, total_skipped = asyncio.run(_run_concurrent())
    else:
        async def _run_sequential() -> tuple[int, int]:
            grand_collected = 0
            grand_skipped = 0

            for i, (dt, source_name) in enumerate(plan, 1):
                click.echo(f"\n[{i}/{len(plan)}] {dt.value} <- {source_name}")
                tracker = _ProgressTracker(
                    f"{source_name}/{dt.value}", total=limit,
                )
                collected, skipped = await collect_from_source(
                    source_name,
                    dt,
                    data_dir,
                    since=_parse_date(since),
                    until=_parse_date(until),
                    limit=limit,
                    skip_existing=skip_existing,
                    skip_content=skip_content,
                    progress=tracker,
                )
                click.echo(
                    f"  {source_name}/{dt.value}: {collected} collected, {skipped} skipped"
                )
                grand_collected += collected
                grand_skipped += skipped

            return grand_collected, grand_skipped

        total_collected, total_skipped = asyncio.run(_run_sequential())

    click.echo(
        f"\nTotal: {total_collected} collected, {total_skipped} skipped "
        f"across {len(plan)} document types"
    )


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
@click.option("--type", "doc_type", default=None,
              type=click.Choice([dt.value for dt in DocType]),
              help="Only validate this document type.")
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
                        issues.append((
                            "WARN",
                            f"Session {session} doesn't match date year {doc_year}",
                        ))
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
@click.argument("command", default="juris")
def man(command: str) -> None:
    """Display manual pages for juris commands."""
    man_dir = Path(__file__).resolve().parent.parent.parent / "man"
    page = man_dir / f"{command}.1"
    if not page.exists():
        available = sorted(p.stem for p in man_dir.glob("*.1"))
        raise click.UsageError(
            f"No manual page for '{command}'. "
            f"Available: {', '.join(available)}"
        )
    click.echo(page.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
