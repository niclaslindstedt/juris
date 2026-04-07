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

## SEE ALSO

[juris(1)](juris), [collect](collect), [collect-type](collect-type)
