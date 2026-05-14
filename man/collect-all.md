# juris-collect-all(1)

## NAME

juris collect-all - collect all document types from all providers

## SYNOPSIS

```
juris collect-all [OPTIONS]
```

## DESCRIPTION

Collect every document type using the best provider for each type.
When multiple providers support the same document type, only the
preferred provider is used. Selection prefers structured APIs over
web scraping for reliability and speed.

Preferred providers for overlapping types:

| Types | Provider | Reason |
|---|---|---|
| prop, sou, dir, skr | riksdagen | JSON API, faster, reliable |
| ds, lagr | regeringen | Sole provider |

Use `--dry-run` to preview the full collection plan before running.

## OPTIONS

- `--since DATE` — Collect documents from this date (`YYYY-MM-DD`).
- `--until DATE` — Collect documents until this date (`YYYY-MM-DD`).
- `--limit N` — Maximum number of documents per document type.
- `--skip-existing / --no-skip-existing` — Skip already collected documents. Default: enabled.
- `--skip-content / --no-skip-content` — Skip fetching full text (metadata only). Default: disabled.
- `--max-age DUR` — Skip (source, type) pairs whose last unfiltered run finished within this window.
  Accepts a duration like `6h`, `30m`, `1d` (or seconds as a bare integer). Pass `0` to disable.
  Default: `6h`. The check only fires when the invocation itself has no filters (no `--since`,
  `--until`, `--session`, or `--limit`), so filtered runs always execute.
- `--validate` — Before skipping an already-collected document, verify the JSON parses, the
  companion `.md` file exists, and every attachment with a recorded `local_path` is present and
  non-empty on disk. Failed checks trigger a re-fetch. Disables `--max-age` (the freshness
  short-circuit cannot be combined with on-disk validation). Default: disabled.
- `--dry-run` — Show the collection plan (provider per type), then exit.

## COLLECTION PLAN

The plan iterates through every DocType in order and maps each to
its preferred provider. Types without a known provider are skipped.
The full list of type-to-provider mappings can be seen with `--dry-run`.

## EXAMPLES

Preview the collection plan:

```sh
juris collect-all --dry-run
```

Collect everything from 2025 onwards (metadata only):

```sh
juris collect-all --since 2025-01-01 --skip-content
```

Collect everything with a limit of 10 per type:

```sh
juris collect-all --limit 10
```

Force a re-run even if the last collect-all was recent:

```sh
juris collect-all --max-age 0
```

Skip types that ran within the last day (longer freshness window):

```sh
juris collect-all --max-age 1d
```

Validate on-disk completeness for every enumerated document and re-fetch the broken ones:

```sh
juris collect-all --validate
```

## INCREMENTAL BEHAVIOR

`collect-all` does two layers of work avoidance:

1. **Freshness short-circuit (`--max-age`)** — When a (source, type) pair's
   last unfiltered run completed within the window, the pair is skipped
   entirely with no API calls. Tracked via `last_full_run_at` in
   `.state/{source}_{doc_type}.json`. Only counts fully completed unfiltered
   runs; failed or partial runs do not refresh the timestamp.
2. **Auto-incremental (`since`)** — When a pair is not skipped by freshness,
   `since` is auto-set to `last_fetched_date - 2 days` so the collector only
   enumerates documents newer than what is already stored.

The per-document skip — for each enumerated doc the source returns — checks
only that the JSON file exists on disk. Pass `--validate` for a deeper check:
the JSON must parse into a `Document`, the `.md` must exist, and every
attachment with a `local_path` must exist and be non-empty. Any failure causes
the doc to be re-fetched in this run. `--validate` disables the `--max-age`
freshness short-circuit so the validation actually runs.

## SEE ALSO

[juris(1)](juris), [collect](collect), [collect-type](collect-type)
