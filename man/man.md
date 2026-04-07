# juris-man(1)

## NAME

juris man - display manual pages for juris commands

## SYNOPSIS

```
juris man [COMMAND]
```

## DESCRIPTION

Display the manual page for a juris command. If no command is given,
the main juris(1) manual page is shown.

## ARGUMENTS

- `COMMAND` — The command to show the manual page for. One of: `juris`, `collect`, `collect-type`, `collect-all`, `status`, `stats`, `man`. If omitted, defaults to `juris` (the main manual page).

## EXAMPLES

Show the main manual page:

```sh
juris man
```

Show the collect command manual:

```sh
juris man collect
```

Show the collect-all command manual:

```sh
juris man collect-all
```

## SEE ALSO

[juris(1)](juris)
