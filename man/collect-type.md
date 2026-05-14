# juris-collect-type(1)

## NAME

juris collect-type - collect a document type using the best provider

## SYNOPSIS

```
juris collect-type DOC_TYPE [OPTIONS]
```

## DESCRIPTION

Collect documents of a given type using the preferred (highest quality)
provider. When multiple sources support the same document type, only
the best one is used by default.

Provider selection criteria:

- Structured APIs are preferred over web scraping (reliability).
- Richer metadata and faster collection rates are preferred.

Preferred providers for overlapping types:

| Types | Provider | Reason |
|---|---|---|
| prop, sou, dir, skr | riksdagen | JSON API, faster, reliable |
| ds, lagr | regeringen | Sole provider |

Pass `--all-providers` to collect from every source that supports the
given type. Use `--dry-run` to preview which providers would be used.

## ARGUMENTS

- `DOC_TYPE` — The document type to collect. One of: `prop`, `sou`, `mot`, `bet`, `ds`, `lagr`, `dir`, `skr`, `sfs`, `nja`, `ad`, `hfd`, `mod`, `pmod`, `jo`, `jk`, `foreskrift`, `eu_reg`, `eu_dir`, `cjeu`, `echr`.

## OPTIONS

- `--session SESSION` — Parliamentary session or year to filter by.
- `--since DATE` — Collect documents from this date (`YYYY-MM-DD`).
- `--until DATE` — Collect documents until this date (`YYYY-MM-DD`).
- `--limit N` — Maximum number of documents per provider.
- `--skip-existing / --no-skip-existing` — Skip already collected documents. Default: enabled.
- `--skip-content / --no-skip-content` — Skip fetching full text (metadata only). Default: disabled.
- `--max-age DUR` — Skip a provider entirely if its last unfiltered run finished within this window (e.g. `6h`, `1d`). Default `0` (disabled). Only fires for unfiltered invocations.
- `--dry-run` — Show which providers would be used, then exit without collecting.
- `--all-providers` — Use all providers that support the type, not just the preferred one.

## EXAMPLES

Collect propositions using the best provider:

```sh
juris collect-type prop --session 2024/25
```

Preview providers for SOU:

```sh
juris collect-type sou --dry-run
```

Collect SOU from all providers:

```sh
juris collect-type sou --all-providers --since 2024-01-01
```

Collect Supreme Court decisions:

```sh
juris collect-type nja --limit 50
```

## SEE ALSO

[juris(1)](juris), [collect](collect), [collect-all](collect-all)
