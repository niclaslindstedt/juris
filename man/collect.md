# juris-collect(1)

## NAME

juris collect - collect documents from a specific source

## SYNOPSIS

```
juris collect SOURCE --type TYPE [OPTIONS]
```

## DESCRIPTION

Collect documents from a named source. The source determines which API
or website is scraped, and the `--type` option selects the document type.

Each source only supports a subset of document types. If an unsupported
type is requested, the command exits with an error listing the types
that source supports.

Documents are saved as JSON and Markdown under the data directory.
Collection state is tracked per source/type pair so that subsequent
runs can skip already-collected documents.

## ARGUMENTS

- `SOURCE` — The data source to collect from. One of: `riksdagen`, `regeringen`, `domstol`, `jo_jk`, `lagrummet`, `eur_lex`, `curia`, `hudoc`.

## OPTIONS

- `--type TYPE` — *(Required)* Document type to collect. Valid types depend on the source. See [juris(1)](juris).
- `--session SESSION` — Parliamentary session (e.g. `2024/25`) or year (e.g. `2025`). Filters results to the given session. Interpretation varies by source: Riksdagen uses riksmote, Domstol converts years to date ranges, EU sources convert years to date ranges.
- `--since DATE` — Collect documents from this date onwards (`YYYY-MM-DD` format).
- `--until DATE` — Collect documents up to this date (`YYYY-MM-DD` format).
- `--limit N` — Maximum number of documents to collect. Useful for testing or sampling a source.
- `--skip-existing / --no-skip-existing` — Skip documents that have already been saved to disk. Enabled by default. Use `--no-skip-existing` to re-collect and overwrite.
- `--skip-content / --no-skip-content` — Skip fetching full text content (HTML, PDF). Collects metadata only, which is much faster. Disabled by default.

## SOURCE DETAILS

### riksdagen

Uses the Riksdagen open data JSON API at data.riksdagen.se.
Supports: `prop`, `sou`, `mot`, `bet`, `dir`, `skr`, `sfs`.
Paginates via the API's built-in `@nasta_sida` links.
Fetches full HTML content per document unless `--skip-content`.
Rate limit: 0.5s between requests.

### regeringen

Scrapes document listing and detail pages from www.regeringen.se.
Supports: `prop`, `sou`, `ds`, `lagr`, `dir`, `skr`.
Extracts designation, date, department, and PDF attachments
from HTML. Rate limit: 1.0s between requests.

### domstol

Uses the Domstolsverket case law REST API.
Supports: `nja` (Supreme Court), `ad` (Labour Court),
`hfd` (Supreme Administrative Court), `mod` (Land & Environment
Court of Appeal), `pmod` (Patent & Market Court of Appeal).
Downloads PDF attachments and extracts text. Strips standard
court letterhead from extracted text.
Rate limit: 0.5s between requests.

### jo_jk

Scrapes decisions from JO (www.jo.se) and JK (www.jk.se).
Supports: `jo`, `jk`.
JO uses sitemap-based URL discovery. JK uses listing page
scraping with pagination. Extracts decision metadata from
detail pages including diarienummer and beslutsdatum.
Rate limit: 1.0s between requests.

### lagrummet

Scrapes regulatory agency rules (foreskrifter) from individual
Swedish agency websites. Currently supports AFS (Arbetsmiljoverket)
and SOSFS/HSLF-FS (Socialstyrelsen).
Supports: `foreskrift`.
Rate limit: 1.0s between requests.

### eur_lex

Queries the EU CELLAR SPARQL endpoint for EU legislation.
Supports: `eu_reg` (regulations), `eu_dir` (directives).
Fetches Swedish titles with English fallback. Optionally
retrieves full text from EUR-Lex HTML pages.
Rate limit: 1.0s between requests.

### curia

Queries the EU CELLAR SPARQL endpoint for CJEU judgments.
Supports: `cjeu`.
Filters for judgments containing "CJ" in the CELEX number.
Optionally retrieves full text from EUR-Lex.
Rate limit: 1.0s between requests.

### hudoc

Queries the HUDOC JSON search API for ECtHR judgments.
Supports: `echr`.
Filters for judgments against Sweden (respondent: SWE).
Attempts to fetch full judgment HTML from the HUDOC conversion
endpoint (not always available).
Rate limit: 1.0s between requests.

## EXAMPLES

Collect recent propositions from Riksdagen:

```sh
juris collect riksdagen --type prop --since 2025-01-01
```

Collect Supreme Court decisions for 2024:

```sh
juris collect domstol --type nja --session 2024
```

Collect JO decisions (metadata only, limit 10):

```sh
juris collect jo_jk --type jo --skip-content --limit 10
```

Collect EU regulations:

```sh
juris collect eur_lex --type eu_reg --session 2025
```

Collect ds from Regeringen (sole provider):

```sh
juris collect regeringen --type ds --limit 5
```

## SEE ALSO

[juris(1)](juris), [collect-type](collect-type), [collect-all](collect-all)
