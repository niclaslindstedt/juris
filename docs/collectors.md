# Collectors

## Overview

Collectors are the components that know how to talk to a specific data
source. Each collector connects to one external API or website and converts
its responses into the unified `Document` model that juris uses internally.

The collector framework is built around three concepts:

1. **BaseCollector** — an abstract base class that provides HTTP helpers,
   retry logic, rate limiting, and attachment downloading
2. **Auto-discovery** — collectors register themselves automatically when
   imported, with no manual configuration needed
3. **Registry** — a central lookup that maps source names and document
   types to collector classes

## BaseCollector

All collectors extend `BaseCollector`, defined in `collectors/base.py`.

### Required Class Variables

```python
class MyCollector(BaseCollector):
    source = Source.MY_SOURCE                    # Which source this collector represents
    supported_doc_types = [DocType.X, DocType.Y] # Document types it can collect
    preferred_for = [DocType.X]                  # Optional: types where this is the default
```

### Required Methods

Every collector must implement two abstract methods:

**`collect()`** — The main collection method. An async generator that yields
`Document` objects one at a time:

```python
async def collect(
    self,
    doc_type: DocType,
    *,
    session: str | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
    skip_content: bool = False,
) -> AsyncIterator[Document]:
    ...
```

Parameters:
- `doc_type`: Which document type to collect
- `session`: Filter by session/year (e.g., `"2024/25"`)
- `since` / `until`: Date range filter
- `limit`: Maximum number of documents to yield
- `skip_content`: If true, skip fetching full text (metadata only)

**`get_document()`** — Fetch a single document by its source-specific ID:

```python
async def get_document(self, source_id: str) -> Document | None:
    ...
```

### Provided HTTP Helpers

BaseCollector provides several methods for making HTTP requests:

**`_fetch_with_retry(url, **kwargs)`** — GET request with automatic retry
on transient errors (429, 5xx, timeouts). Uses exponential backoff with
configurable parameters.

**`_download_file(url, dest)`** — Stream-download a file to disk with
retry support.

**`download_attachments(doc, data_dir)`** — Download all attachments for
a document and extract text from the primary (first) PDF attachment.

### Rate Limiting

Each collector has a `RateLimiter` instance that enforces a minimum delay
between requests. Default intervals vary by source:

| Source | Rate Limit |
|---|---|
| Riksdagen | 0.5s |
| Regeringen | 1.0s |
| Domstol | 0.5s |
| JO/JK | 1.0s |
| Lagrummet | 1.0s |
| EUR-Lex | 1.0s |
| CURIA | 1.0s |
| HUDOC | 1.0s |

### Retry Strategy

The default retry configuration:
- **Max retries**: 3 (4 total attempts)
- **Backoff base**: 1.0 second
- **Backoff factor**: 2.0 (exponential: 1s, 2s, 4s)
- **Retryable errors**: 429 (Too Many Requests), 5xx (Server Error),
  connection timeouts

When a 429 response includes a `Retry-After` header, the collector
respects the specified wait time.

## Auto-Discovery

Collectors register themselves automatically through Python's
`__init_subclass__()` mechanism. When a class inherits from
`BaseCollector`, it is added to the internal `_COLLECTOR_REGISTRY`
keyed by its `source` value.

The registry is populated lazily: the first time any registry function
is called, `_ensure_discovered()` imports every `.py` file in the
`collectors/` package (excluding files starting with `_` and `base.py`).
This triggers `__init_subclass__()` for each collector class.

Files starting with `_` (like `_cellar.py`) are excluded from
auto-discovery and are used for shared helpers.

## Registry Functions

Four functions provide access to the collector registry:

**`get_registry()`** — Returns the full `dict[str, type[BaseCollector]]`
mapping source names to collector classes.

**`get_collector_class(source)`** — Look up a single collector class by
source name. Returns `None` if not found.

**`get_doc_type_providers()`** — Returns a `dict[str, list[str]]` mapping
each document type to the list of source names that support it.

**`get_preferred_providers()`** — Returns a `dict[str, str]` mapping each
document type to its preferred source. For types with only one provider,
that provider is automatically preferred. For types with multiple providers,
the one declaring `preferred_for` wins.

## The preferred_for Mechanism

When multiple collectors support the same document type, the
`preferred_for` class variable declares the default. For example:

```python
class RiksdagenCollector(BaseCollector):
    source = Source.RIKSDAGEN
    supported_doc_types = [DocType.PROP, DocType.SOU, DocType.MOT, ...]
    preferred_for = [DocType.PROP, DocType.SOU, DocType.DIR, DocType.SKR]
```

This means when you run `juris collect-type prop`, it uses the Riksdagen
collector by default. The `--all-providers` flag overrides this and
collects from every available source.

Types with only a single provider (e.g., court decisions from Domstol)
don't need explicit `preferred_for` — they are automatically preferred.

## Adding a New Collector

To add a collector for a new data source:

### Step 1: Add the source to the enum

In `src/juris/models.py`, add a new member to the `Source` enum:

```python
class Source(StrEnum):
    # ... existing sources
    my_source = "my_source"  # Description of the source
```

### Step 2: Create the collector file

Create `src/juris/collectors/mysource.py`:

```python
from collections.abc import AsyncIterator
from datetime import date

from juris.collectors.base import BaseCollector
from juris.models import DocType, Document, Source
from juris.utils import build_doc_id, html_to_text


class MySourceCollector(BaseCollector):
    source = Source.MY_SOURCE
    supported_doc_types = [DocType.SOME_TYPE]
    preferred_for = [DocType.SOME_TYPE]  # optional

    async def collect(
        self,
        doc_type: DocType,
        *,
        session: str | None = None,
        since: date | None = None,
        until: date | None = None,
        limit: int | None = None,
        skip_content: bool = False,
    ) -> AsyncIterator[Document]:
        # Fetch documents from the source
        # Yield Document objects one at a time
        ...

    async def get_document(self, source_id: str) -> Document | None:
        # Fetch a single document by its source ID
        ...
```

### Step 3: Done

No changes are needed in `cli.py`, `__init__.py`, or any registry file.
The collector is automatically discovered and registered when its module
is imported. The CLI commands `collect`, `collect-type`, and `collect-all`
will immediately recognize the new source and its document types.

## Existing Collectors

| Collector | Source | Access Method | Document Types |
|---|---|---|---|
| `RiksdagenCollector` | data.riksdagen.se | JSON API | prop, sou, mot, bet, dir, skr, sfs |
| `RegeringenCollector` | regeringen.se | Web Scraping | prop, sou, ds, lagr, dir, skr |
| `DomstolCollector` | domstol.se | REST API | nja, ad, hfd, mod, pmod |
| `JoJkCollector` | jo.se / jk.se | Web Scraping | jo, jk |
| `LagrummetCollector` | lagrummet.se | Web Scraping | foreskrift |
| `EurLexCollector` | eur-lex.europa.eu | SPARQL | eu_reg, eu_dir |
| `CuriaCollector` | curia.europa.eu | SPARQL | cjeu |
| `HudocCollector` | hudoc.echr.coe.int | JSON API | echr |

See [data-sources](data-sources) for details on each source's API,
quirks, and field mappings.
