# juris-report(1)

## NAME

juris report - generate and manage collection coverage reports

## SYNOPSIS

```
juris report [--json] [--save]
juris report list
juris report show ID
juris report diff ID
```

## DESCRIPTION

Generate a collection coverage report showing document counts, date ranges,
and per-year breakdowns for all document types. Reports can be saved for
later comparison.

## SUBCOMMANDS

| Subcommand | Description |
|---|---|
| *(none)* | Generate and display a new report. |
| `list` | List all saved reports. |
| `show ID` | Display a previously saved report by ID (prefix match supported). |
| `diff ID` | Compare a saved report against the current state. |

## OPTIONS

- `--json` — Output the report as JSON instead of formatted text.
- `--save` — Save the report for later comparison (implied by default).

## EXAMPLES

Generate a report:

```sh
juris report
```

Generate and output as JSON:

```sh
juris report --json
```

List saved reports:

```sh
juris report list
```

Show a saved report by ID prefix:

```sh
juris report show a1b2c3d4
```

Compare a previous report with current state:

```sh
juris report diff a1b2c3d4
```

## SEE ALSO

[juris(1)](juris), [stats](stats), [status](status)
