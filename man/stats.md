# juris-stats(1)

## NAME

juris stats - count collected documents per type

## SYNOPSIS

```
juris stats
```

## DESCRIPTION

Count and display the number of collected documents for each document
type. Scans the data directory for JSON files under each type
subdirectory and prints the counts.

Only types with at least one collected document are shown.

## OUTPUT FORMAT

One line per document type with collected documents:

```
<doc_type>: <count>
```

Followed by a total line:

```
total: <N>
```

If the data directory does not exist, a message is shown.

## EXAMPLES

Count all collected documents:

```sh
juris stats
```

Count documents in a custom data directory:

```sh
juris --data-dir /path/to/data stats
```

## SEE ALSO

[juris(1)](juris), [status](status)
