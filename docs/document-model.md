# Document Model

## Overview

Every document collected by juris is represented as a `Document` — a
Pydantic model defined in `src/juris/models.py`. Regardless of whether
a document comes from a JSON API, a scraped web page, or a SPARQL
endpoint, it is normalized into this single structure before being saved.

## The Document Model

```python
class Document(BaseModel):
    doc_id: str               # Canonical ID (e.g., "prop-2024/25:208")
    doc_type: DocType         # One of 21 document types
    designation: str          # Number or reference (e.g., "208", "42", CELEX)
    session: str | None       # Riksmöte or year (e.g., "2024/25", "2024")
    title: str                # Document title
    summary: str | None       # First substantial paragraph, max 500 chars
    text: str | None          # Cleaned plain text body
    html: str | None          # Raw HTML (fallback when text unavailable)
    date: date                # Publication or decision date
    department: str | None    # Ministry, agency, or court name
    committee: str | None     # For committee reports (BET type)
    status: str | None        # Legal status metadata
    source: Source            # Which collector produced this document
    source_id: str | None     # Original ID in the source system
    source_url: str | None    # URL to the original document
    fetched_at: datetime      # When the document was collected
    attachments: list[Attachment]  # PDF/DOCX file references
```

### Field Details

**`doc_id`** — The canonical identifier used for filenames, deduplication,
and cross-referencing. Built by `utils.build_doc_id()`:

```
With session:    {doc_type}-{session}:{designation}   → prop-2024/25:208
Without session: {doc_type}-{designation}             → sou-42
```

**`doc_type`** — One of the 21 document types in the `DocType` enum.
Determines the storage directory and how the document is categorized.

**`designation`** — The document's number or reference within its type.
Format varies by type: a simple number for propositions, a diarienummer
for ombudsman decisions, a CELEX number for EU documents.

**`session`** — The parliamentary session (e.g., `"2024/25"`) or year
(e.g., `"2024"`). Used as a subdirectory in storage. When not provided
by the source, inferred from the document date.

**`title`** — The document's title. For sources that provide it directly
(Riksdagen, HUDOC), used as-is. For scraped sources, extracted from the
first `<h1>` element.

**`summary`** — A brief excerpt, max 500 characters. Extracted by finding
the first paragraph longer than 60 characters in the text body. Some
sources provide dedicated summary fields.

**`text`** — The document's cleaned plain text content. Extracted from
HTML via `html_to_text()`, from PDFs via PyMuPDF, or directly from API
fields. This is the primary content field.

**`html`** — Raw HTML content when available. Kept as a fallback for
cases where the plain text extraction loses important formatting.

**`date`** — The publication or decision date. Parsed from ISO format,
Swedish date strings, or SPARQL date literals. Falls back to today's
date if unparseable (with a warning).

**`department`** — The responsible ministry, agency, or court. Examples:
`"Justitiedepartementet"`, `"Högsta domstolen"`,
`"Court of Justice of the European Union"`.

**`committee`** — Only populated for BET (committee report) documents.
Extracted from the designation prefix using a committee map (e.g.,
`"JuU"` → `"Justitieutskottet"`).

**`source`** — Which collector produced this document. One of the 8
values in the `Source` enum.

**`source_id`** — The document's ID in the original source system.
For example, a Riksdagen `dok_id`, a HUDOC `itemid`, or a CELEX number.

**`source_url`** — URL to the original document in the source system,
useful for linking back to the authoritative version.

**`attachments`** — List of file references (typically PDFs) associated
with the document. Each attachment has a filename, URL, MIME type,
optional file size, and optional local path after download.

## DocType Enum

The 21 document types are organized into five categories:

### Swedish Parliament

| Value | Description |
|---|---|
| `prop` | Propositioner (government bills) |
| `mot` | Motioner (parliamentary motions) |
| `bet` | Betänkanden (committee reports) |
| `skr` | Skrivelser (government communications) |

### Swedish Government

| Value | Description |
|---|---|
| `sou` | Statens offentliga utredningar (public inquiries) |
| `ds` | Departementsserien (department series) |
| `dir` | Kommittédirektiv (committee directives) |
| `lagr` | Lagrådsremisser (legal council referrals) |
| `sfs` | Svensk författningssamling (Swedish Code of Statutes) |

### Courts

| Value | Description |
|---|---|
| `nja` | Nytt Juridiskt Arkiv (Supreme Court) |
| `ad` | Arbetsdomstolens domar (Labour Court) |
| `hfd` | Högsta förvaltningsdomstolens årsbok (Supreme Admin. Court) |
| `mod` | Mark- och miljööverdomstolens avgöranden (Land & Env. Court) |
| `pmod` | Patent- och marknadsöverdomstolens avgöranden (Patent Court) |

### Authorities

| Value | Description |
|---|---|
| `jo` | Justitieombudsmannens beslut (Parliamentary Ombudsman) |
| `jk` | Justitiekanslerns beslut (Chancellor of Justice) |
| `foreskrift` | Myndighetsföreskrifter (regulatory agency rules) |

### EU Law

| Value | Description |
|---|---|
| `eu_reg` | EU regulations (förordningar) |
| `eu_dir` | EU directives (direktiv) |
| `cjeu` | CJEU judgments (EU-domstolen) |
| `echr` | ECtHR judgments (Europadomstolen) |

## Source Enum

| Value | Description |
|---|---|
| `riksdagen` | Swedish Parliament open data API |
| `regeringen` | Swedish Government publications |
| `domstol` | Swedish courts decision API |
| `jo_jk` | Parliamentary & Chancellor of Justice ombudsmen |
| `lagrummet` | Agency regulations and guidelines |
| `eur_lex` | EU regulations and directives via CELLAR |
| `curia` | Court of Justice of the EU via CELLAR |
| `hudoc` | European Court of Human Rights |

## Attachment Model

```python
class Attachment(BaseModel):
    filename: str             # e.g., "prop-2024-25_208.pdf"
    url: str                  # Download URL
    mime_type: str | None     # e.g., "application/pdf"
    size: int | None          # File size in bytes
    local_path: str | None    # Path after download (relative to data dir)
```

Attachments are downloaded during the collection pipeline and stored
under `data/{doc_type}/{session}/attachments/`. Text is extracted from
the primary (first) PDF attachment and merged into the document's `text`
field when it provides richer content than the scraped text.

## Document ID Construction

The `build_doc_id()` function in `utils.py` constructs canonical IDs:

```python
build_doc_id("prop", "208", "2024/25")  # → "prop-2024/25:208"
build_doc_id("sou", "42", "2024")       # → "sou-2024:42"
build_doc_id("echr", "12345/20")        # → "echr-12345/20"
```

Rules:
- Type prefix is always the `DocType` value
- Session and designation are separated by `:`
- When no session is provided, the colon is omitted

## Filename Sanitization

The `sanitize_filename()` function converts doc IDs to safe filenames:

- `/` → `-` (forward slash to hyphen)
- `:` → `_` (colon to underscore)
- ` ` → `-` (space to hyphen)

Example: `prop-2024/25:208` → `prop-2024-25_208`

## Validation Rules

The test suite enforces quality standards on every document:

- **Required fields**: `doc_id`, `doc_type`, `designation`, `title`,
  `date`, `source` must be present and non-empty
- **ID prefix**: `doc_id` must start with the `doc_type` value
- **Title quality**: Must be longer than 3 characters
- **Date range**: Year must be ≥ 1900 and not in the future
- **Designation**: Must be ≤ 200 characters and not a URL
- **Session format**: Must match `^\d{4}(/\d{2})?$` when present
- **Model validity**: Must be loadable as a Pydantic `Document` instance
