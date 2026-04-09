# juris-logs(1)

## NAME

juris logs - show collection run logs

## SYNOPSIS

```
juris logs [--type TYPE] [--source SOURCE] [--limit N]
```

## DESCRIPTION

Display structured logs from previous collection runs. Each collection run
produces a JSONL log file in the `.logs/` directory with per-document
status entries and a run summary.

## OPTIONS

- `--type TYPE` — Filter logs by document type.
- `--source SOURCE` — Filter logs by source.
- `--limit N` — Maximum number of log entries to show.

## EXAMPLES

Show recent collection logs:

```sh
juris logs
```

Show logs for proposition collections:

```sh
juris logs --type prop
```

## SEE ALSO

[juris(1)](juris), [status](status), [report](report)
