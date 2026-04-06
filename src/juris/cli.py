"""CLI entry point for juris."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from pathlib import Path

import click

from juris.collectors.curia import CjeuCollector
from juris.collectors.domstol import DomstolCollector
from juris.collectors.eurlex import EurLexCollector
from juris.collectors.hudoc import HudocCollector
from juris.collectors.jo_jk import JoJkCollector
from juris.collectors.lagrummet import LagrummetCollector
from juris.collectors.regeringen import RegeringenCollector
from juris.collectors.riksdagen import RiksdagenCollector
from juris.models import DocType, Source
from juris.state import load_state, save_state
from juris.storage import document_exists, save_document

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path("data")

COLLECTORS = {
    "riksdagen": RiksdagenCollector,
    "regeringen": RegeringenCollector,
    "domstol": DomstolCollector,
    "jo_jk": JoJkCollector,
    "lagrummet": LagrummetCollector,
    "eur_lex": EurLexCollector,
    "curia": CjeuCollector,
    "hudoc": HudocCollector,
}


def _build_doc_type_providers() -> dict[str, list[str]]:
    """Map each doc_type to the list of source names supporting it."""
    mapping: dict[str, list[str]] = {}
    for source_name, collector_cls in COLLECTORS.items():
        for dt in collector_cls.supported_doc_types:
            mapping.setdefault(dt.value, []).append(source_name)
    return mapping


DOC_TYPE_PROVIDERS = _build_doc_type_providers()

# Best provider for each document type when multiple sources overlap.
# Selection criteria:
#   - Structured API > web scraping (reliability)
#   - Richer metadata and faster collection rate
#
# Riksdagen (JSON API) beats Regeringen (scraping) for: prop, sou, dir, skr.
# Regeringen is kept exclusively for ds and lagr (no other source has them).
PREFERRED_PROVIDERS: dict[str, str] = {
    dt: providers[0] for dt, providers in DOC_TYPE_PROVIDERS.items()
    if len(providers) == 1
}
# Explicit overrides for doc types with multiple providers
PREFERRED_PROVIDERS.update({
    "prop": "riksdagen",  # Structured API, reliable beteckning field
    "sou": "riksdagen",   # Structured API, faster pagination
    "dir": "riksdagen",   # Structured API, built-in session filtering
    "skr": "riksdagen",   # Structured API, single request per doc
})


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


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
@click.argument("source", type=click.Choice(list(COLLECTORS.keys())))
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
    src = Source(source)

    collector_cls = COLLECTORS[source]
    collector = collector_cls()

    if dt not in collector.supported_doc_types:
        supported = ", ".join(t.value for t in collector.supported_doc_types)
        raise click.UsageError(
            f"Source '{source}' does not support type '{doc_type}'. "
            f"Supported types: {supported}"
        )

    state = load_state(data_dir, src, dt)

    async def _run() -> int:
        collected = 0
        skipped = 0
        try:
            async for doc in collector.collect(
                dt,
                session=session,
                since=_parse_date(since),
                until=_parse_date(until),
                limit=limit,
                skip_content=skip_content,
            ):
                exists = document_exists(
                    doc.doc_id, doc.doc_type, doc.session, data_dir,
                )
                if skip_existing and exists:
                    skipped += 1
                    click.echo(f"  skip {doc.doc_id} (exists)")
                    continue

                if not skip_content:
                    doc = await collector.download_attachments(doc, data_dir)

                path = save_document(doc, data_dir)
                collected += 1
                click.echo(f"  saved {doc.doc_id} -> {path}")

                state.total_collected += 1
                if not state.last_fetched_date or str(doc.date) > state.last_fetched_date:
                    state.last_fetched_date = str(doc.date)
        finally:
            await collector.close()

        save_state(state, data_dir)
        click.echo(f"\nDone: {collected} collected, {skipped} skipped")
        return collected

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

    if all_providers:
        providers = DOC_TYPE_PROVIDERS.get(doc_type, [])
    else:
        preferred = PREFERRED_PROVIDERS.get(doc_type)
        providers = [preferred] if preferred else []

    if not providers:
        raise click.UsageError(f"No providers found for document type '{doc_type}'.")

    all_available = DOC_TYPE_PROVIDERS.get(doc_type, [])
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

        for source_name in providers:
            src = Source(source_name)
            collector = COLLECTORS[source_name]()
            state = load_state(data_dir, src, dt)

            click.echo(f"\n--- {source_name} ---")
            collected = 0
            skipped = 0
            try:
                async for doc in collector.collect(
                    dt,
                    session=session,
                    since=_parse_date(since),
                    until=_parse_date(until),
                    limit=limit,
                    skip_content=skip_content,
                ):
                    exists = document_exists(
                        doc.doc_id, doc.doc_type, doc.session, data_dir,
                    )
                    if skip_existing and exists:
                        skipped += 1
                        click.echo(f"  skip {doc.doc_id} (exists)")
                        continue

                    if not skip_content:
                        doc = await collector.download_attachments(doc, data_dir)

                    path = save_document(doc, data_dir)
                    collected += 1
                    click.echo(f"  saved {doc.doc_id} -> {path}")

                    state.total_collected += 1
                    if not state.last_fetched_date or str(doc.date) > state.last_fetched_date:
                        state.last_fetched_date = str(doc.date)
            finally:
                await collector.close()

            save_state(state, data_dir)
            click.echo(f"  {source_name}: {collected} collected, {skipped} skipped")
            grand_collected += collected
            grand_skipped += skipped

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
@click.pass_context
def collect_all(
    ctx: click.Context,
    since: str | None,
    until: str | None,
    limit: int | None,
    skip_existing: bool,
    skip_content: bool,
    dry_run: bool,
) -> None:
    """Collect all document types from all providers (best source per type).

    When multiple providers support the same document type, only the
    best provider is used.  Selection prefers structured APIs over web
    scraping for reliability and speed.

    \b
    Preferred providers for overlapping types:
      prop, sou, dir, skr  ->  riksdagen  (JSON API, faster, reliable)
      ds, lagr             ->  regeringen (sole provider)
    """
    data_dir: Path = ctx.obj["data_dir"]

    # Build the plan: list of (doc_type, source_name) pairs
    plan: list[tuple[DocType, str]] = []
    for dt in DocType:
        source_name = PREFERRED_PROVIDERS.get(dt.value)
        if source_name:
            plan.append((dt, source_name))
        else:
            logger.warning("No preferred provider for %s, skipping", dt.value)

    if dry_run:
        click.echo("Collection plan (best provider per document type):\n")
        for dt, source_name in plan:
            providers = DOC_TYPE_PROVIDERS.get(dt.value, [])
            alt = [p for p in providers if p != source_name]
            alt_str = f"  (skipped: {', '.join(alt)})" if alt else ""
            click.echo(f"  {dt.value:12s} <- {source_name}{alt_str}")
        click.echo(f"\n{len(plan)} document types across "
                    f"{len({s for _, s in plan})} providers")
        return

    click.echo(
        f"Collecting {len(plan)} document types from "
        f"{len({s for _, s in plan})} providers"
    )

    async def _run_all() -> tuple[int, int]:
        grand_collected = 0
        grand_skipped = 0

        for dt, source_name in plan:
            src = Source(source_name)
            collector = COLLECTORS[source_name]()
            state = load_state(data_dir, src, dt)

            click.echo(f"\n--- {dt.value} <- {source_name} ---")
            collected = 0
            skipped = 0
            try:
                async for doc in collector.collect(
                    dt,
                    since=_parse_date(since),
                    until=_parse_date(until),
                    limit=limit,
                    skip_content=skip_content,
                ):
                    exists = document_exists(
                        doc.doc_id, doc.doc_type, doc.session, data_dir,
                    )
                    if skip_existing and exists:
                        skipped += 1
                        click.echo(f"  skip {doc.doc_id} (exists)")
                        continue

                    if not skip_content:
                        doc = await collector.download_attachments(doc, data_dir)

                    path = save_document(doc, data_dir)
                    collected += 1
                    click.echo(f"  saved {doc.doc_id} -> {path}")

                    state.total_collected += 1
                    if not state.last_fetched_date or str(doc.date) > state.last_fetched_date:
                        state.last_fetched_date = str(doc.date)
            finally:
                await collector.close()

            save_state(state, data_dir)
            click.echo(f"  {source_name}/{dt.value}: {collected} collected, {skipped} skipped")
            grand_collected += collected
            grand_skipped += skipped

        return grand_collected, grand_skipped

    total_collected, total_skipped = asyncio.run(_run_all())
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


if __name__ == "__main__":
    main()
