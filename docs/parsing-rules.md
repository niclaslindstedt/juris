# Parsing Rules

How juris normalizes documents from heterogeneous Swedish legal data sources
into a unified `Document` model.

## Overview

Each data source (Riksdagen API, Regeringen.se, Domstolsverket, etc.) returns
documents in a different format: JSON APIs, HTML pages, SPARQL results, or PDF
files. The parsing layer converts every source format into a single Pydantic
`Document` model defined in `src/juris/models.py`.

The goal is **structural consistency**: regardless of source, every document
has the same fields, ID format, filename conventions, and quality standards.

## Parsing Pipeline

```
Source API / Web Page / SPARQL Endpoint
        |
        v
    Collector._parse_*()          # Source-specific parsing
        |
        v
    Document model (Pydantic)     # Unified representation
        |
        v
    storage.save_document()       # Dual output: JSON + Markdown
        |
        +-- data/{type}/{session}/{id}.json   (full model dump)
        +-- data/{type}/{session}/{id}.md     (YAML frontmatter + text)
```

## The Document Model

Defined in `src/juris/models.py`. Every collector must produce a valid instance.

| Field         | Type              | Required | Description                                  |
|---------------|-------------------|----------|----------------------------------------------|
| `doc_id`      | `str`             | Yes      | Canonical ID, e.g. `prop-2024/25:208`        |
| `doc_type`    | `DocType` (enum)  | Yes      | One of 21 document types                     |
| `designation` | `str`             | Yes      | Number/beteckning, e.g. `208`, `42`, CELEX   |
| `session`     | `str \| None`     | No       | Riksmöte (`2024/25`) or year (`2024`)        |
| `title`       | `str`             | Yes      | Document title                               |
| `summary`     | `str \| None`     | No       | First substantial paragraph, max 500 chars   |
| `text`        | `str \| None`     | No       | Cleaned plain text                           |
| `html`        | `str \| None`     | No       | Raw HTML fallback                            |
| `date`        | `date`            | Yes      | Publication/decision date                    |
| `department`  | `str \| None`     | No       | Ministry, agency, or court name              |
| `committee`   | `str \| None`     | No       | For committee reports (BET)                  |
| `status`      | `str \| None`     | No       | Legal status metadata                        |
| `source`      | `Source` (enum)   | Yes      | Which collector produced this document       |
| `source_id`   | `str \| None`     | No       | Original ID in the source system             |
| `source_url`  | `str \| None`     | No       | URL to the original document                 |
| `fetched_at`  | `datetime`        | Yes      | When the document was collected              |
| `attachments` | `list[Attachment]` | No      | PDF/DOCX file references                     |

## Consistency Rules

These rules apply to **all collectors** and ensure uniform output.

### 1. Document ID Construction

Built by `utils.build_doc_id(doc_type, designation, session)`:

```
With session:    "{doc_type}-{session}:{designation}"   -> prop-2024/25:208
Without session: "{doc_type}-{designation}"             -> sou-42
```

The `doc_id` is the canonical identifier used for filenames, deduplication,
and cross-referencing.

### 2. Filename Sanitization

Built by `utils.sanitize_filename(doc_id)`:

- `/` -> `-`
- `:` -> `_`
- ` ` -> `-`

Example: `prop-2024/25:208` -> `prop-2024-25_208`

### 3. Summary Extraction

Standard pattern used across all collectors:

```python
for paragraph in re.split(r"\n{2,}", text):
    stripped = paragraph.strip()
    if len(stripped) > 60:
        summary = stripped[:500]
        break
```

Rules:
- Split text on double newlines (paragraph boundaries)
- Skip paragraphs shorter than **60 characters** (headings, metadata lines)
- Truncate to **500 characters** maximum
- Skip paragraphs that match the document title (Riksdagen)
- Some sources provide a dedicated summary field (e.g. `undertitel` from Riksdagen,
  `sammanfattning` from Domstolsverket, `conclusion` from HUDOC)

### 4. Date Handling

- **Primary**: Parse from source data (ISO format `YYYY-MM-DD` preferred)
- **Swedish dates**: Parsed by `utils.parse_swedish_date()` for dates like
  `"02 april 2026"`
- **Fallback**: `date.today()` when no date can be parsed (with a warning log)

### 5. Text Extraction

Priority order:
1. **API text field** (Riksdagen HTML, Domstolsverket `innehall`)
2. **Web page content** via `utils.extract_page_content()` with UI stripping
3. **PDF text** via `pdf.extract_text()` using PyMuPDF

PDF text replaces scraped text when it is **more than 2x longer**, indicating
the PDF has richer content than the web page summary.

UI elements stripped before text extraction:
- `<nav>`, `<header>`, `<aside>`, `<footer>`, `<button>`
- Cookie banners, social share widgets, breadcrumbs
- "Lyssna", "Dela sidan", "Kopiera lank" buttons

### 6. Session Inference

When the source does not provide a session/year:
- Infer from `date.year` as a plain 4-digit string
- Riksdagen provides `rm` (riksmote) directly: `"2024/25"`
- SFS uses the year from the `YYYY:NNN` beteckning as session

### 7. HTML to Text

`utils.html_to_text(html)`:
- Removes `<script>` and `<style>` elements
- Extracts text with `\n` separator between elements
- Collapses 3+ consecutive newlines to 2
- Strips leading/trailing whitespace

## Provider-Specific Rules

### Riksdagen (`riksdagen.py`)

**Source**: `https://data.riksdagen.se` JSON API
**Doc types**: prop, sou, mot, bet, dir, skr, sfs
**Rate limit**: 0.5s

| Field         | Extraction                                                |
|---------------|-----------------------------------------------------------|
| `designation` | `item["beteckning"]`, fallback `item["nummer"]`           |
| `session`     | `item["rm"]`                                              |
| `title`       | `item["titel"]`                                           |
| `date`        | `item["datum"]` (ISO format)                              |
| `department`  | `item["organ"]`                                           |
| `summary`     | `item["undertitel"]`, fallback first paragraph >60 chars   |
| `text`        | Full HTML from `/dokument/{dok_id}.json` -> `html_to_text` |
| `source_id`   | `item["dok_id"]`                                          |

**Special rules**:
- **SFS**: Designation `YYYY:NNN` is split: year becomes `session`, NNN becomes `designation`
- **BET**: Committee name extracted from designation prefix (e.g. `JuU15` -> `Justitieutskottet`)
  via `_COMMITTEE_MAP` lookup
- Attachments from `filbilaga.fil` array in API response

### Regeringen (`regeringen.py`)

**Source**: `https://www.regeringen.se` web scraping
**Doc types**: prop, sou, ds, lagr, dir, skr
**Rate limit**: 1.0s

| Field         | Extraction                                                |
|---------------|-----------------------------------------------------------|
| `designation` | Regex patterns per doc type on full page text              |
| `session`     | From designation regex group 1, fallback `date.year`       |
| `title`       | First `<h1>` element                                      |
| `date`        | "Publicerad DD manad YYYY" pattern -> `parse_swedish_date` |
| `department`  | Link text from `<a href="/tx/...">` elements              |
| `text`        | `extract_page_content(soup)` with UI stripping             |

**Designation regex patterns** (`_DESIGNATION_PATTERNS`):
- Prop: `Prop\.\s*(\d{4}/\d{2}):(\d+)` -> ("229", "2025/26")
- SOU: `SOU\s+(\d{4}):(\d+)` -> ("42", "2024")
- Ds: `Ds\s+(\d{4}):(\d+)` or `ds[- ](\d{4})[- :](\d+)`
- Dir: `Dir\.\s*(\d{4}):(\d+)`
- Skr: `Skr\.\s*(\d{4}/\d{2}):(\d+)`
- Lagr: `Lagradsremiss\s+(\d{4}):(\d+)`

**Fallback chain for designation**:
1. Full page text
2. `<title>` tag text
3. URL path
4. URL slug (last resort)

**Special rules**:
- **LAGR**: If designation parsing fails, downloads first PDF and tries
  `extract_lagr_designation()` for patterns in PDF metadata/first page
- PDF sizes parsed from link text: `"(pdf 2 MB)"`

### Domstolsverket (`domstol.py`)

**Source**: `https://rattspraxis.etjanst.domstol.se` JSON API
**Doc types**: nja, ad, hfd, mod, pmod
**Rate limit**: 0.5s

| Field         | Extraction                                                |
|---------------|-----------------------------------------------------------|
| `designation` | Court-specific reference parser on `referatNummerLista`    |
| `session`     | Year from reference or decision date                       |
| `title`       | `pub["benamning"]`, fallback from reference/case numbers   |
| `date`        | `pub["avgorandedatum"]` (ISO format)                      |
| `department`  | `pub["domstol"]["domstolNamn"]`                           |
| `text`        | `pub["innehall"]` (may be HTML, cleaned if so)             |
| `summary`     | `pub["sammanfattning"]`                                    |

**Reference parsers** (each returns `(designation, session)`):
- **NJA**: `NJA\s+(\d{4}):(\d+)` or `NJA\s+(\d{4})\s+s\.\s*(\d+)` (prefers colon format)
- **AD**: `AD\s+(\d{4})\s+nr\s+(\d+)`
- **HFD**: `(?:HFD|RA)\s+(\d{4})\s+ref\.\s*(\d+)` (handles legacy RA format)
- **MOD**: `MOD\s+(\d{4}):(\d+)`
- **PMOD**: Falls back to NJA parser (no dedicated pattern)

**Fallback chain for designation**:
1. Reference parser on `referatNummerLista`
2. First case number from `malNummerLista` (spaces removed)
3. `pub["id"]` or literal `"unknown"`

**Special rules**:
- Court letterhead stripped from PDF text via `_strip_court_header()`
  (matches `Dok.Id \d+ ... Sida N (M)` block)
- Attachment URLs use URL-encoded `fillagringId` path

### JO/JK (`jo_jk.py`)

**Source**: `https://www.jo.se` (sitemap) / `https://www.jk.se` (listing pages)
**Doc types**: jo, jk
**Rate limit**: 1.0s

| Field         | Extraction                                                |
|---------------|-----------------------------------------------------------|
| `designation` | Diarienummer regex: `Diarienummer[:\s]+(\d{1,5}[-]\d{2,4})` |
| `session`     | Year from diarienummer (4-digit or 2-digit with `20` prefix) |
| `title`       | First `<h1>` element                                       |
| `date`        | `Beslutsdatum[:\s]+(\d{4}-\d{2}-\d{2})`, fallback ISO anywhere |
| `department`  | `Beslutsfattare` regex extraction                          |
| `text`        | `extract_page_content(soup)` with UI stripping             |

**URL discovery**:
- **JO**: Parses 20 sitemap XML files (`resolve-sitemap1.xml` through `resolve-sitemap20.xml`),
  filters URLs matching `/besluten/`
- **JK**: Paginates through listing pages at `/beslut/`, extracts links from
  `<article>` elements or decision URL patterns

**Fallback chain for designation**:
1. Diarienummer from page text
2. URL slug

### Lagrummet (`lagrummet.py`)

**Source**: Individual agency websites (av.se, socialstyrelsen.se, etc.)
**Doc types**: foreskrift
**Rate limit**: 1.0s

| Field         | Extraction                                                |
|---------------|-----------------------------------------------------------|
| `designation` | Regex: `([A-ZAOAO][\w-]*FS)\s+(\d{4}):(\d+)` -> `"AFS 2023:1"` |
| `session`     | Year from designation                                      |
| `title`       | First `<h1>` or `<h2>` (skipping cookie banners)          |
| `date`        | `Beslutsdatum/Publicerad/Utfardad` + ISO or Swedish date   |
| `department`  | From `_AgencyConfig.agency_name`                           |
| `text`        | `extract_page_content(soup)` with UI stripping             |

**Supported agencies** (`_AGENCIES` config):
- **AFS** (Arbetsmiljoverket): Single listing page, not paginated
- **SOSFS** (Socialstyrelsen): Paginated listing
- **HSLF-FS** (Socialstyrelsen): Paginated listing, same base URL as SOSFS

**Fallback chain for designation**:
1. Foreskrift regex on page text
2. Foreskrift regex on URL
3. URL slug

### EUR-Lex (`eurlex.py`)

**Source**: EU Publications Office CELLAR SPARQL endpoint
**Doc types**: eu_reg, eu_dir
**Rate limit**: 1.0s, timeout 60s

| Field         | Extraction                                                |
|---------------|-----------------------------------------------------------|
| `designation` | CELEX number from SPARQL `?celex` binding                  |
| `session`     | `date.year` as string                                      |
| `title`       | Swedish title preferred, English fallback, CELEX last resort |
| `date`        | `?date` binding (ISO format)                               |
| `department`  | `"European Union (regulation)"` or `"European Union (directive)"` |
| `text`        | Full HTML from EUR-Lex page (Swedish, then English)        |

**SPARQL query**: Filters by resource type URI (REG or DIR), excludes
corrigenda via `FILTER(!CONTAINS(STR(?celex), "R("))`.

### CURIA (`curia.py`)

**Source**: EU Publications Office CELLAR SPARQL endpoint
**Doc types**: cjeu
**Rate limit**: 1.0s, timeout 60s

| Field         | Extraction                                                |
|---------------|-----------------------------------------------------------|
| `designation` | CELEX number from SPARQL `?celex` binding                  |
| `session`     | `date.year` as string                                      |
| `title`       | Swedish title preferred, English fallback                  |
| `date`        | `?date` binding (ISO format)                               |
| `department`  | `"Court of Justice of the European Union"`                 |
| `source_id`   | ECLI if available, otherwise CELEX                         |
| `text`        | Full HTML from EUR-Lex page                                |

**SPARQL query**: Filters for JUDG resource type with `CONTAINS(STR(?celex), "CJ")`.

### HUDOC (`hudoc.py`)

**Source**: `https://hudoc.echr.coe.int` JSON search API
**Doc types**: echr
**Rate limit**: 1.0s

| Field         | Extraction                                                |
|---------------|-----------------------------------------------------------|
| `designation` | Application number (`appno`), first value before `;`       |
| `session`     | `date.year` as string                                      |
| `title`       | `docname` from API, fallback to designation                |
| `date`        | `judgmentdate` (ISO format prefix)                         |
| `department`  | `"European Court of Human Rights"`                         |
| `summary`     | `conclusion` + `article` fields joined with `"; "`         |
| `text`        | Multi-strategy: Swedish HTML -> English -> French -> PDF   |

**Disambiguation**: When multiple items share the same `appno` (e.g. chamber
vs grand chamber decisions), appends last 6 chars of `itemid` to designation
to ensure unique `doc_id`.

**Query**: Filters for `respondent:"SWE"` and `documentcollectionid:"JUDGMENTS"`.

## Document Type Matrix

| DocType     | Provider(s)          | Designation Format       | Session Format |
|-------------|----------------------|--------------------------|----------------|
| `prop`      | riksdagen, regeringen| Number (e.g. `208`)      | `YYYY/YY`      |
| `sou`       | riksdagen, regeringen| Number (e.g. `42`)       | `YYYY`         |
| `mot`       | riksdagen            | Beteckning               | `YYYY/YY`      |
| `bet`       | riksdagen            | Committee+number         | `YYYY/YY`      |
| `ds`        | regeringen           | Number (e.g. `6`)        | `YYYY`         |
| `lagr`      | regeringen           | Number or DNR            | `YYYY`         |
| `dir`       | riksdagen, regeringen| Number (e.g. `100`)      | `YYYY`         |
| `skr`       | riksdagen, regeringen| Number (e.g. `10`)       | `YYYY/YY`      |
| `sfs`       | riksdagen            | Number (year split off)  | `YYYY`         |
| `nja`       | domstol              | Ref number (e.g. `19`)   | `YYYY`         |
| `ad`        | domstol              | Nr (e.g. `19`)           | `YYYY`         |
| `hfd`       | domstol              | Ref number (e.g. `56`)   | `YYYY`         |
| `mod`       | domstol              | Number (e.g. `26`)       | `YYYY`         |
| `pmod`      | domstol              | Number or case number    | `YYYY`         |
| `jo`        | jo_jk                | Diarienummer             | `YYYY`         |
| `jk`        | jo_jk                | Diarienummer             | `YYYY`         |
| `foreskrift` | lagrummet           | `PREFIX YYYY:N`          | `YYYY`         |
| `eu_reg`    | eur_lex              | CELEX number             | `YYYY`         |
| `eu_dir`    | eur_lex              | CELEX number             | `YYYY`         |
| `cjeu`      | curia                | CELEX number             | `YYYY`         |
| `echr`      | hudoc                | Application number       | `YYYY`         |

## Known Edge Cases

1. **URL slug fallbacks**: When designation parsing fails for Regeringen,
   Lagrummet, or JO/JK, the URL slug is used as designation. This produces
   human-readable but non-standard IDs like `prop-2025:my-document-slug`.

2. **Date fallback**: All collectors fall back to `date.today()` when date
   parsing fails, which can pollute historical collections. A warning is
   always logged.

3. **PDF text preference**: PDF-extracted text replaces scraped text only when
   it is more than 2x longer (`len(pdf_text) > len(doc.text) * 2`). This
   heuristic avoids replacing good web text with corrupt PDF extraction, but
   has no absolute quality threshold.

4. **HUDOC disambiguation**: Multiple HUDOC items can share the same
   application number. The collector appends the last 6 characters of
   `itemid` to the designation to create unique document IDs.

5. **Committee extraction**: Only known committee prefixes (AU, CU, FiU, etc.)
   are recognized. Unknown prefixes silently return `None` for the committee
   field.

6. **SFS designation split**: SFS beteckning `YYYY:NNN` is split so that the
   year becomes the session and NNN becomes the designation, unlike other
   Riksdagen types where `beteckning` is used directly.

7. **LAGR PDF extraction**: When web scraping fails to extract a lagr
   designation, the collector downloads the first PDF attachment and searches
   its metadata and first page for designation patterns.
