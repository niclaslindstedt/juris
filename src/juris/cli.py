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
) -> None:
    """Collect a document type from all supporting providers."""
    data_dir: Path = ctx.obj["data_dir"]
    dt = DocType(doc_type)

    providers = DOC_TYPE_PROVIDERS.get(doc_type, [])
    if not providers:
        raise click.UsageError(f"No providers found for document type '{doc_type}'.")

    if dry_run:
        click.echo(f"Providers for '{doc_type}': {', '.join(providers)}")
        return

    click.echo(
        f"Collecting {doc_type} from {len(providers)} provider(s): "
        f"{', '.join(providers)}"
    )

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
