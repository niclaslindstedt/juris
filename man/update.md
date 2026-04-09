# juris-update(1)

## NAME

juris update - update the remote document index

## SYNOPSIS

```
juris update --type TYPE [--limit N] [--source SOURCE]
```

## DESCRIPTION

Enumerate documents available from a remote source and build a local index.
The index tracks which documents exist remotely, enabling comparison with
locally collected documents to identify gaps.

Index files are stored in the `.index/` directory under the data directory.
Updates are resumable — subsequent runs continue from where the previous
run left off.

## OPTIONS

- `--type TYPE` — The document type to index (required).
- `--limit N` — Maximum number of entries to fetch per run.
- `--source SOURCE` — Override the default source for this document type.

## EXAMPLES

Update the proposition index:

```sh
juris update --type prop --limit 100
```

Update with a specific source:

```sh
juris update --type sou --source regeringen
```

## SEE ALSO

[juris(1)](juris), [collect](collect), [status](status)
