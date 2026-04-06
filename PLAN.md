# Juris Harmonization & Improvement Plan

## Context: What Testing Revealed

I downloaded 25 documents across all 8 sources. Here's what I found:

### Critical Quality Issues

1. **lagrummet (foreskrift)**: Cookie consent banner captured as document title ("Den här webbplatsen använder kakor"). Social sharing buttons ("Instagram", "Facebook", "LinkedIn", "Dela sidan", "Kopiera länk") pollute the summary and text fields. The `extract_page_content()` utility is not stripping cookie banners or social widgets.

2. **jo_jk (JO decisions)**: UI artifacts in summary/text: "Lyssna", "Dela sidan", "Kopiera länk", "(+)" buttons. The `extract_page_content()` function captures these interactive UI elements.

3. **regeringen**: Only gets ~5K chars of page summary text, while riksdagen gets ~400K chars from PDFs for the *same document*. The PDF is downloaded but `download_attachments()` won't overwrite text since `doc.text` is already set (line 139 of `base.py`: `if primary_text and not doc.text`). The scraper sets `text=summary_text` from the web page, which blocks PDF extraction.

4. **eur_lex/curia**: EUR-Lex HTML endpoint returns 404 for many CELEX numbers (especially corrigenda like `R(02)`, `R(05)`). SPARQL query returns these corrigenda/amendments by default. Title falls back to raw CELEX number (e.g., "32024R1624R(02)") instead of a human-readable title. CJEU returned **0 results** — the SPARQL query may need a broader filter or the court URI may have changed.

5. **hudoc (ECHR)**: Full text conversion endpoint returns 404 for most items. Documents saved as metadata-only shells. Duplicate doc_id collision: two different HUDOC items (001-249223 and 001-249566) map to the same `appno` "32694/23", causing the second to be skipped.

6. **domstol (NJA)**: Court letterhead/address block ("Dok.Id 350410", "Riddarhustorget 8", "08-561 666 00", etc.) pollutes the first ~15 lines of extracted PDF text.

### Structural Inconsistencies Across Collectors

7. **Text field semantics**: Some collectors set `text` to scraped page content (regeringen, jo_jk, lagrummet), blocking PDF text extraction. Others leave `text=None` and let `download_attachments()` fill it from PDFs (riksdagen, domstol). This is the root cause of the thin content from web scrapers.

8. **Summary field quality**: Riksdagen uses `undertitel` (clean). JO uses first 500 chars of page scrape (includes "Lyssna", "(+)"). Lagrummet uses first 500 chars (includes social buttons). ECHR uses conclusion text (good). EUR-Lex has no summary.

9. **Date fallback**: All web scrapers fall back to `date.today()` silently when date parsing fails, which can produce incorrect dates that are never flagged.

---

## Implementation Plan

### Phase 1: Fix `extract_page_content()` to strip UI junk (affects jo_jk, lagrummet, regeringen)

**File**: `src/juris/utils.py` — `extract_page_content()` function (line 61)

**Changes**:
- Add stripping of common UI elements before extracting text: cookie consent banners, social share widgets, "Lyssna" buttons, breadcrumbs
- Decompose elements matching common patterns: `[class*="cookie"]`, `[class*="share"]`, `[class*="social"]`, `[aria-label*="Lyssna"]`, `button` tags, elements with `class*="breadcrumb"`
- This single fix ripples through jo_jk, lagrummet, and regeringen since they all call `extract_page_content()`

### Phase 2: Fix text field priority — let PDF text win over thin page scrapes

**File**: `src/juris/collectors/base.py` — `download_attachments()` (line 100)

**Changes**:
- Change the guard from `if primary_text and not doc.text` to: `if primary_text and (not doc.text or len(primary_text) > len(doc.text) * 2)` — prefer PDF text when it's substantially richer
- This fixes the regeringen, jo_jk, and lagrummet collectors which set `doc.text` to short page scrapes that then block the much richer PDF extraction

### Phase 3: Fix lagrummet title extraction (cookie banner as title)

**File**: `src/juris/collectors/lagrummet.py` — `_parse_detail_page()` (line 147)

**Changes**:
- After getting `h1` text, check if it looks like a cookie banner (contains "kakor" or "cookies") and fall back to the designation or the next `h1`/`h2`
- Also try to extract the actual regulation title from the page content using the designation pattern as an anchor

### Phase 4: Fix EUR-Lex SPARQL query to filter out corrigenda/amendments

**File**: `src/juris/collectors/eurlex.py` — `_EURLEX_QUERY_TEMPLATE` (line 29)

**Changes**:
- Add a SPARQL FILTER to exclude CELEX numbers containing `R(` (corrigenda indicators): `FILTER(!CONTAINS(?celex, "R("))`
- This prevents collecting documents that almost always 404 on the EUR-Lex HTML endpoint

### Phase 5: Fix CJEU collector (0 results)

**File**: `src/juris/collectors/curia.py` — `_CJEU_QUERY_TEMPLATE` (line 23)

**Changes**:
- Debug the SPARQL query: the court URI or resource-type may have changed
- Add fallback: if zero results with current query, try without the court filter and with a broader resource type
- Add `LIMIT 50` default to prevent empty pages from breaking pagination

### Phase 6: Fix HUDOC duplicate doc_id from shared appno

**File**: `src/juris/collectors/hudoc.py` — `_parse_result()` (line 78)

**Changes**:
- When multiple HUDOC items share the same `appno`, disambiguate by appending the `itemid` suffix to the designation
- Track seen designations within a collection run to detect and handle collisions

### Phase 7: Clean court letterhead from domstol PDF text

**File**: `src/juris/collectors/domstol.py` or `src/juris/pdf.py`

**Changes**:
- Add a post-processing step in the domstol collector's `download_attachments` (or override it) to strip the standard court header block from extracted PDF text
- Use a regex to detect and remove the boilerplate pattern (Dok.Id, Besöksadress, Telefon, Öppettider, Postadress, E-post, Webbplats, Sida N (M))

### Phase 8: Harmonize summary field quality

**File**: Multiple collectors

**Changes**:
- `jo_jk.py`: Extract summary from the actual decision summary paragraph on the page (the text after the tag categories and before "Ladda ner"), not from `extract_page_content()` output
- `lagrummet.py`: Extract summary from the `1 §` (purpose clause) of the regulation, not from page scrape
- Ensure all summaries are clean text without UI artifacts

### Phase 9: Add date parsing warnings

**File**: `src/juris/utils.py` and relevant collectors

**Changes**:
- When falling back to `date.today()`, emit a warning log so users know a date couldn't be parsed
- This is a small observability improvement across all web-scraping collectors
