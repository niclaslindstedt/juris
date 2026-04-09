# juris-search(1)

## NAME

juris search - search for legal documents

## SYNOPSIS

```
juris search QUERY [--type TYPE] [--source SOURCE] [--local-only] [--provider-only] [--limit N]
```

## DESCRIPTION

Search for documents matching a query string. By default, searches both
local collected documents and remote provider APIs. Results are sorted
by date (newest first) and deduplicated.

## ARGUMENTS

- `QUERY` — The search term to find in document titles, designations, summaries, and text content.

## OPTIONS

- `--type TYPE` — Filter results to a specific document type.
- `--source SOURCE` — Filter results to a specific source.
- `--local-only` — Only search locally collected documents (no API calls).
- `--provider-only` — Only search via provider APIs (skip local).
- `--limit N` — Maximum number of results to return (default: 50).

## EXAMPLES

Search local documents:

```sh
juris search "yttrandefrihet" --local-only
```

Search for propositions only:

```sh
juris search "dataskydd" --type prop
```

Search via providers:

```sh
juris search "Article 10" --provider-only --source hudoc
```

## SEE ALSO

[juris(1)](juris), [collect](collect)
