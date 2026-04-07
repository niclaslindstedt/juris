# Data Sources

## Overview

juris collects from 8 data sources spanning Swedish national institutions
and European courts. Each source uses a different access method — JSON APIs,
web scraping, REST APIs, or SPARQL endpoints — but all produce the same
unified `Document` model.

This page describes each source: what it provides, how it is accessed, and
any notable behaviors or limitations.

## Riksdagen (Swedish Parliament)

**URL**: data.riksdagen.se
**Method**: JSON API
**Rate Limit**: 0.5s
**Document Types**: prop, sou, mot, bet, dir, skr, sfs
**Preferred For**: prop, sou, dir, skr

The Riksdagen open data API is the most structured source. It provides
paginated JSON responses with document metadata and full HTML content
available via separate requests.

**Key behaviors**:
- Full document HTML is fetched separately per document using the `dok_id`
- Committee names for BET documents are extracted from the designation
  prefix (e.g., `JuU15` → Justitieutskottet)
- SFS documents have their `YYYY:NNN` designation split: the year becomes
  the session and NNN becomes the designation
- Pagination follows `@nasta_sida` (next page) links in API responses
- Attachments are extracted from the `filbilaga.fil` array

## Regeringen (Swedish Government)

**URL**: regeringen.se
**Method**: Web Scraping
**Rate Limit**: 1.0s
**Document Types**: prop, sou, ds, lagr, dir, skr
**Preferred For**: (none — sole provider for ds and lagr)

Regeringen.se is scraped using BeautifulSoup. Documents are discovered
through listing pages and then parsed from detail pages.

**Key behaviors**:
- Two-step process: listing page → detail page
- Designations are extracted via regex patterns specific to each doc type
- Dates are parsed from Swedish text ("Publicerad DD månad YYYY")
- Departments are extracted from internal links (`/tx/` paths)
- For lagrådsremisser (lagr), if designation parsing fails on the web page,
  the collector downloads the first PDF and searches its metadata and headers
- PDF file sizes are parsed from link text (e.g., "(pdf 2 MB)")
- Multiple fallback strategies for designation extraction: page text,
  title tag, URL path, URL slug

## Domstolsverket (Swedish Courts)

**URL**: domstol.se
**Method**: REST API
**Rate Limit**: 0.5s
**Document Types**: nja, ad, hfd, mod, pmod

The court decisions API provides paginated JSON results for five court types.
Each court has its own reference format that requires dedicated parsing.

**Key behaviors**:
- Each court type maps to a code: HDO (Supreme Court), ADO (Labour Court),
  HFD (Admin. Court), MOD (Land & Environment), PMOD (Patent & Market)
- Reference parsers extract designations from `referatNummerLista`:
  - NJA: `NJA YYYY:N` (preferred) or `NJA YYYY s. N`
  - AD: `AD YYYY nr N`
  - HFD: `HFD YYYY ref. N` or legacy `RA YYYY ref. N`
  - MÖD: `MÖD YYYY:N`
- Court letterhead is stripped from PDF-extracted text using a regex pattern
  matching `Dok.Id ... Sida N (M)` blocks
- Fallback chain for designations: reference number → case number → pub ID

## JO/JK (Ombudsmen)

**URL**: jo.se / jk.se
**Method**: Web Scraping
**Rate Limit**: 1.0s
**Document Types**: jo, jk

JO (Parliamentary Ombudsman) and JK (Chancellor of Justice) decisions are
collected from their respective websites using different discovery strategies.

**Key behaviors**:
- **JO**: URL discovery via XML sitemaps (`resolve-sitemap1.xml` through
  `resolve-sitemap20.xml`), filtering for `/besluten/` paths
- **JK**: URL discovery by scraping paginated listing pages at `/beslut/`
- Both use the same detail page parser
- Designations are diarienummer extracted via regex
- Dates come from "Beslutsdatum" fields on the page
- Departments come from "Beslutsfattare" fields

## Lagrummet (Regulatory Agencies)

**URL**: Various agency websites
**Method**: Web Scraping
**Rate Limit**: 1.0s
**Document Types**: foreskrift

Collects regulatory rules (föreskrifter) from Swedish agency websites.
Currently supports three agency prefixes.

**Supported agencies**:

| Prefix | Agency | Website |
|---|---|---|
| AFS | Arbetsmiljöverket | av.se |
| SOSFS | Socialstyrelsen | socialstyrelsen.se |
| HSLF-FS | Socialstyrelsen | socialstyrelsen.se |

**Key behaviors**:
- Each agency has its own configuration: prefix, agency name, listing URL
- Designation format: `PREFIX YYYY:N` (e.g., `AFS 2023:1`)
- Some agencies use paginated listings, others have a single page
- Dates are extracted from "Beslutsdatum", "Publicerad", or "Utfärdad" fields

## EUR-Lex (EU Regulations & Directives)

**URL**: eur-lex.europa.eu (via Publications Office CELLAR)
**Method**: SPARQL
**Rate Limit**: 1.0s
**Timeout**: 60s
**Document Types**: eu_reg, eu_dir

EU regulations and directives are collected through SPARQL queries against
the EU Publications Office CELLAR endpoint.

**Key behaviors**:
- SPARQL queries filter by resource type URI (regulations vs directives)
- Corrigenda are excluded via `FILTER(!CONTAINS(STR(?celex), "R("))`
- Swedish titles are preferred; English is the fallback
- Full text is fetched from EUR-Lex HTML pages (Swedish, then English)
- CELEX number serves as both designation and source ID
- Pagination uses SPARQL OFFSET/LIMIT

## CURIA (Court of Justice of the EU)

**URL**: curia.europa.eu (via Publications Office CELLAR)
**Method**: SPARQL
**Rate Limit**: 1.0s
**Timeout**: 60s
**Document Types**: cjeu

CJEU judgments are collected through the same CELLAR SPARQL endpoint as
EUR-Lex, with different filters.

**Key behaviors**:
- Filters for JUDG (judgment) resource type with `CONTAINS(STR(?celex), "CJ")`
- ECLI identifier is used as source_id when available
- Full text fetched from EUR-Lex HTML pages
- Summary extracted from the first substantial paragraph
- Shares helper functions with EUR-Lex via the `_cellar.py` module

## HUDOC (European Court of Human Rights)

**URL**: hudoc.echr.coe.int
**Method**: JSON API
**Rate Limit**: 1.0s
**Document Types**: echr

ECHR judgments against Sweden are collected from the HUDOC search API.

**Key behaviors**:
- Filters for `respondent:"SWE"` and `documentcollectionid:"JUDGMENTS"`
- Application number (`appno`) is used as the designation
- When multiple items share the same application number (e.g., chamber vs
  grand chamber), the last 6 characters of `itemid` are appended for
  uniqueness
- Full text uses a multi-strategy approach:
  1. Swedish HTML conversion
  2. English HTML conversion
  3. French HTML conversion
  4. PDF conversion as final fallback
- Summary is built from `conclusion` and `article` fields

## Source Comparison

| Source | Method | Types | Rate | Notes |
|---|---|---|---|---|
| Riksdagen | JSON API | 7 | 0.5s | Most structured, preferred for shared types |
| Regeringen | Scraping | 6 | 1.0s | Sole provider for ds, lagr |
| Domstol | REST API | 5 | 0.5s | Court-specific reference parsing |
| JO/JK | Scraping | 2 | 1.0s | Sitemap (JO) vs listing pages (JK) |
| Lagrummet | Scraping | 1 | 1.0s | Multi-agency configuration |
| EUR-Lex | SPARQL | 2 | 1.0s | Swedish text preferred |
| CURIA | SPARQL | 1 | 1.0s | Shares CELLAR helpers with EUR-Lex |
| HUDOC | JSON API | 1 | 1.0s | Multi-language text fallback |

For detailed field mapping and parsing rules per source, see
[parsing-rules](parsing-rules).
