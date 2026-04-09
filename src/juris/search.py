"""Document search — local and provider-based."""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

from juris.collectors.base import get_collector_class, get_searchable_sources
from juris.models import DocType, SearchResult, Source
from juris.storage import document_exists

logger = logging.getLogger(__name__)

# Maximum snippet length (chars on each side of match)
_SNIPPET_CONTEXT = 60


def _make_snippet(text: str, pattern: re.Pattern[str]) -> str | None:
    """Extract a short text excerpt around the first match."""
    m = pattern.search(text)
    if not m:
        return None
    start = max(0, m.start() - _SNIPPET_CONTEXT)
    end = min(len(text), m.end() + _SNIPPET_CONTEXT)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def search_local(
    query: str,
    data_dir: Path,
    *,
    doc_type: DocType | None = None,
    source: Source | None = None,
    limit: int = 50,
) -> list[SearchResult]:
    """Search through collected documents on disk."""
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results: list[SearchResult] = []

    # Determine which directories to scan
    if doc_type:
        type_dirs = [data_dir / doc_type.value]
    else:
        type_dirs = (
            [d for d in data_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
            if data_dir.exists()
            else []
        )

    for type_dir in type_dirs:
        if not type_dir.exists():
            continue
        for json_path in type_dir.rglob("*.json"):
            if len(results) >= limit:
                break
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.debug("Skipping %s: %s", json_path, e)
                continue

            # Filter by source if requested
            if source and data.get("source") != source.value:
                continue

            # Search across fields
            match_found = False
            snippet: str | None = None

            for field in ("title", "designation", "summary", "text"):
                value = data.get(field)
                if not value or not isinstance(value, str):
                    continue
                if pattern.search(value):
                    match_found = True
                    if field in ("text", "summary"):
                        snippet = _make_snippet(value, pattern)
                    break

            # If matched on title/designation, try to generate snippet from text/summary
            if match_found and not snippet:
                for fallback in ("text", "summary"):
                    fb_value = data.get(fallback)
                    if fb_value and isinstance(fb_value, str):
                        snippet = _make_snippet(fb_value, pattern)
                        if snippet:
                            break

            if not match_found:
                continue

            doc_date: date | None = None
            if data.get("date"):
                try:
                    doc_date = date.fromisoformat(data["date"])
                except ValueError:
                    pass

            try:
                dt = DocType(data["doc_type"])
                src = Source(data["source"])
            except (ValueError, KeyError):
                continue

            results.append(
                SearchResult(
                    doc_id=data.get("doc_id", ""),
                    doc_type=dt,
                    title=data.get("title", ""),
                    designation=data.get("designation", ""),
                    session=data.get("session"),
                    date=doc_date,
                    source=src,
                    source_url=data.get("source_url"),
                    summary=data.get("summary"),
                    snippet=snippet,
                    local=True,
                )
            )

    # Sort by date descending (most recent first), undated at end
    results.sort(key=lambda r: r.date or date.min, reverse=True)
    return results[:limit]


async def search_provider(
    query: str,
    *,
    source: Source | None = None,
    doc_type: DocType | None = None,
    limit: int = 20,
    data_dir: Path | None = None,
) -> list[SearchResult]:
    """Search via provider APIs."""
    searchable = get_searchable_sources()
    if source:
        searchable = [s for s in searchable if s == source.value]

    results: list[SearchResult] = []

    for src_name in searchable:
        collector_cls = get_collector_class(src_name)
        collector = collector_cls()
        try:
            provider_results = await collector.search(
                query,
                doc_type=doc_type,
                limit=limit,
            )
            for r in provider_results:
                # Check local availability
                if data_dir and r.doc_id:
                    r.local = document_exists(
                        r.doc_id,
                        r.doc_type,
                        r.session,
                        data_dir,
                    )
                results.append(r)
        except NotImplementedError:
            pass
        except Exception as e:
            logger.warning("Search failed for %s: %s", src_name, e)
        finally:
            await collector.close()

    return results


async def search_all(
    query: str,
    data_dir: Path,
    *,
    doc_type: DocType | None = None,
    source: Source | None = None,
    local_only: bool = False,
    provider_only: bool = False,
    limit: int = 50,
) -> list[SearchResult]:
    """Combined search: local + provider, deduplicated by doc_id."""
    results_by_key: dict[str, SearchResult] = {}

    def _dedup_key(r: SearchResult) -> str:
        """Build a deduplication key for a search result."""
        if r.doc_id:
            return r.doc_id
        if r.source_url:
            return r.source_url
        # Composite fallback to avoid false dedup on bare title
        return f"{r.source}:{r.doc_type}:{r.designation or r.title}"

    # Local search
    if not provider_only:
        for r in search_local(query, data_dir, doc_type=doc_type, source=source, limit=limit):
            key = _dedup_key(r)
            results_by_key[key] = r

    # Provider search
    if not local_only:
        provider_results = await search_provider(
            query,
            source=source,
            doc_type=doc_type,
            limit=limit,
            data_dir=data_dir,
        )
        for r in provider_results:
            key = _dedup_key(r)
            if key not in results_by_key:
                results_by_key[key] = r
            elif not results_by_key[key].local and r.local:
                # Provider check found it locally — update the flag
                results_by_key[key].local = True

    # Sort by date descending, undated at end
    all_results = sorted(
        results_by_key.values(),
        key=lambda r: r.date or date.min,
        reverse=True,
    )
    return all_results[:limit]
