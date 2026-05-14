# Architecture

## Data Flow

juris follows a pipeline architecture where documents flow from external
sources through a series of processing stages to structured files on disk.

```
External Source (API / Website / SPARQL)
        │
        ▼
  Collector.collect()        → Async generator yielding Documents
        │
        ▼
  Pipeline.collect_from_source()
        │
        ├── Check existence   → Skip if already saved
        ├── Download attachments → Fetch PDFs, extract text
        ├── Save document     → JSON + Markdown to data/
        └── Update state      → Track progress in .state/
```

Every CLI command ultimately calls `collect_from_source()` in the pipeline
module, which orchestrates the interaction between collectors, storage, and
state tracking.

## Module Overview

### cli.py — Command Line Interface

The entry point for all user interaction. Built with Click, it provides
eleven commands: `collect`, `collect-type`, `collect-all`, `update`,
`report`, `search`, `validate`, `status`, `stats`, `logs`, and `man`.
Each collection command constructs the appropriate parameters and
delegates to the pipeline.

The CLI also handles progress reporting through two reporter classes:
`_ProgressTracker` (progress bar) for normal mode and `_VerboseReporter`
(line-per-document) for verbose mode.

### pipeline.py — Collection Orchestration

The reusable core that coordinates a collection run. The main function
`collect_from_source()` accepts a source name, document type, and
filtering options, then:

1. Instantiates the appropriate collector via the registry
2. Loads incremental state for the (source, doc_type) pair
3. Iterates through documents from the collector's async generator
4. Checks whether each document already exists on disk
5. Downloads attachments and extracts PDF text
6. Saves to dual-format storage
7. Updates collection state

The pipeline defines a `ProgressCallback` protocol so callers (like the
CLI) can plug in their own progress reporting without coupling to any
specific UI.

### models.py — Data Models

Defines the unified data representation using Pydantic:

- **Document**: The core model with 17 fields covering identity
  (doc_id, doc_type, designation), content (title, text, html, summary),
  metadata (date, department, committee, status), and provenance
  (source, source_id, source_url, fetched_at, attachments).
- **DocType**: Enum of 21 document types organized by category.
- **Source**: Enum of 8 data sources.
- **Attachment**: File reference with filename, URL, MIME type, and size.

### storage.py — Dual-Format Persistence

Handles writing and reading documents in two formats:

- **JSON**: Complete model dump with all fields. Used for programmatic
  access and data pipelines.
- **Markdown**: YAML frontmatter (metadata) plus extracted text body.
  Designed for human reading and git-friendly diffs.

Both files are written atomically to the same directory path, derived
from the document type and session.

### state.py — Incremental State Tracking

Maintains a `CollectionState` record per (source, doc_type) pair,
stored as JSON files in the `.state/` directory. Tracks:

- `last_fetched_date`: Newest document date seen (for resuming)
- `last_page`: Pagination checkpoint
- `total_collected`: Running count
- `total_available`: API-reported total when known
- `last_run_at`: Timestamp of last run (always updated)
- `last_full_run_at`: Timestamp of last fully-completed unfiltered run;
  drives `--max-age` so repeated `collect-all` invocations can skip
  freshly-completed (source, type) pairs entirely

This allows subsequent collection runs to pick up where they left off,
and lets short-interval re-runs short-circuit without API calls.

### utils.py — Shared Utilities

Common functions used across the codebase:

- **RateLimiter**: Enforces minimum delay between HTTP requests
- **parse_swedish_date()**: Parses dates with Swedish month names
- **extract_page_content()**: Strips UI chrome from HTML pages
- **html_to_text()**: Converts HTML to clean plain text
- **build_doc_id()**: Constructs canonical document IDs
- **sanitize_filename()**: Converts doc IDs to safe filenames

### pdf.py — PDF Text Extraction

Wraps PyMuPDF for text extraction from PDF files:

- **extract_text()**: Reads a local PDF and returns cleaned text
- **extract_text_from_bytes()**: Extracts from in-memory PDF bytes
- **extract_lagr_designation()**: Specialized extraction for
  lagrådsremiss designation from PDF metadata or headers

### collectors/ — Source Collectors

The `collectors/` package contains the `BaseCollector` abstract class,
the auto-discovery registry, and 8 concrete collector implementations.
See [collectors](collectors) for detailed documentation.

## Key Design Patterns

### Auto-Discovery Registry

Collectors register themselves automatically when their module is
imported, using Python's `__init_subclass__()` hook. The registry is
populated lazily on first access by importing all public modules in
the `collectors/` package. This means adding a new collector requires
only creating a new file — no manual registration step.

### Preferred Provider Selection

When multiple collectors support the same document type (e.g., both
Riksdagen and Regeringen can provide propositions), the `preferred_for`
class variable declares which collector should be the default. The
`collect-type` and `collect-all` commands use this to automatically
select the best source. Single-provider types are implicitly preferred.

### Async Everything

All collectors use `async/await` with httpx for non-blocking I/O.
The `collect()` method is an async generator that yields documents
one at a time, allowing the pipeline to process and save documents
as they arrive rather than buffering everything in memory.

### Resilient HTTP

The `BaseCollector` provides `_fetch_with_retry()` which handles:

- Exponential backoff on 5xx errors
- `Retry-After` header respect on 429 (rate limit) responses
- Configurable retry count, backoff base, and backoff factor
- Timeout handling for slow responses
- Rate limiting between requests via `RateLimiter`

### Dual Output

Every document is written to both JSON and Markdown. This is intentional:
JSON preserves the complete model (including fields like `html` and
`attachments` that don't render well in text), while Markdown provides
a clean, diffable, human-readable view with YAML frontmatter for
metadata and the extracted text as the body.

## Concurrency Model

The `collect-all` command can run multiple collection tasks concurrently
using asyncio with a configurable semaphore (`--max-concurrency`). Each
(source, doc_type) pair runs as an independent task. Within each task,
requests are serialized with rate limiting to respect source API limits.
