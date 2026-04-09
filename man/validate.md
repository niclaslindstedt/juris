# juris-validate(1)

## NAME

juris validate - validate collected data quality

## SYNOPSIS

```
juris validate [--type TYPE]
```

## DESCRIPTION

Check collected documents for data quality issues. Validates required fields,
checks for suspicious values, detects duplicate document IDs, and reports
missing content.

## OPTIONS

- `--type TYPE` — Only validate documents of this type.

## CHECKS PERFORMED

- **Required fields**: doc_id, doc_type, designation, title, date, source must be present and non-empty.
- **Duplicate doc_ids**: Flags documents sharing the same doc_id across files.
- **Suspicious designations**: Warns about overly long designations or designations that match the title.
- **Title quality**: Warns about very short titles.
- **Date range**: Warns about dates before 1900 (suspiciously old).
- **Missing content**: Warns when a document has no text, html, or summary.

## EXAMPLES

Validate all documents:

```sh
juris validate
```

Validate only propositions:

```sh
juris validate --type prop
```

## SEE ALSO

[juris(1)](juris), [stats](stats)
