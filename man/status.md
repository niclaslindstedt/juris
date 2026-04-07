# juris-status(1)

## NAME

juris status - show collection state for all sources and document types

## SYNOPSIS

```
juris status
```

## DESCRIPTION

Display the collection state for every source/document-type pair that
has been collected at least once. Shows the total number of documents
collected, the date of the most recently fetched document, and the
timestamp of the last collection run.

State is read from JSON files stored under `<data-dir>/.state/`. If no
state directory exists, a message is shown suggesting to run
`juris collect` first.

## OUTPUT FORMAT

For each tracked pair, one line is printed:

```
<source>/<doc_type>: <N> docs, latest=<date>, last_run=<datetime>
```

Where:

- `source` — The data source name (e.g. `riksdagen`).
- `doc_type` — The document type (e.g. `prop`).
- `N` — Total documents collected across all runs.
- `latest` — ISO date of the newest document seen.
- `last_run` — ISO datetime of the most recent collection run.

## EXAMPLES

Check collection progress:

```sh
juris status
```

Check progress for a custom data directory:

```sh
juris --data-dir /path/to/data status
```

## SEE ALSO

[juris(1)](juris), [stats](stats)
