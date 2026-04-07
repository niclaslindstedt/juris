# CLAUDE.md

## Project Summary

**juris** is a CLI tool that collects and normalizes Swedish legal documents from 8 official sources into a unified, git-friendly format (JSON + Markdown). It supports 21 document types across Swedish and EU law, with incremental collection, async I/O, rate limiting, and PDF text extraction.

## Project Structure

```
src/juris/
├── cli.py              # Click CLI (collect, collect-type, collect-all, status, stats, man)
├── pipeline.py         # Reusable collection pipeline (collect_from_source, ProgressCallback)
├── models.py           # Pydantic models (Document, DocType, Source, Attachment)
├── storage.py          # Dual-format file storage (JSON + Markdown with YAML frontmatter)
├── state.py            # Incremental collection state tracking (.state/ directory)
├── utils.py            # Shared utilities (rate limiting, text extraction, ID building)
├── pdf.py              # PDF text extraction via pymupdf
└── collectors/         # Source-specific async collectors (auto-discovered)
    ├── __init__.py     # Auto-discovery + backward-compatible re-exports
    ├── base.py         # BaseCollector ABC, registry, __init_subclass__ auto-registration
    ├── riksdagen.py    # Riksdagen JSON API
    ├── regeringen.py   # Regeringen.se web scraper
    ├── domstol.py      # Court decisions REST API
    ├── jo_jk.py        # JO/JK ombudsman decisions
    ├── lagrummet.py    # Agency regulations (AFS, HSLF-FS)
    ├── eurlex.py       # EUR-Lex SPARQL
    ├── curia.py        # CJEU SPARQL
    ├── hudoc.py        # ECtHR JSON API
    └── _cellar.py      # EU CELLAR metadata helper
tests/
├── conftest.py         # Pytest fixtures and helpers
├── test_e2e.py         # End-to-end tests (@e2e marker, hits live APIs)
├── test_parsers.py     # Parser validation tests
├── test_registry.py    # Collector auto-discovery and registry tests
├── test_retry.py       # Retry logic tests
└── test_validate.py    # Document validation tests
docs/
└── parsing-rules.md    # Parsing pipeline documentation
man/                    # Manual pages (.1 files) for CLI commands
```

## Tech Stack

- **Python 3.11+** with async/await
- **httpx** — async HTTP client
- **pydantic** — data validation and models
- **beautifulsoup4 + lxml** — HTML/XML parsing
- **click** — CLI framework
- **pymupdf** — PDF text extraction
- **pyyaml** — YAML frontmatter

## Development

```bash
pip install -e ".[dev]"        # Install with dev dependencies
ruff check src/                # Lint
mypy src/                      # Type check (strict mode)
pytest tests/                  # Run unit tests
pytest -m e2e                  # Run e2e tests (live APIs, slow)
```

- Line length: 100
- Ruff rules: E, F, I, W
- MyPy: strict mode, Python 3.11+
- pytest-asyncio with `asyncio_mode = auto`

## Commit and PR Conventions

- Use **conventional commits** for all commit messages (e.g., `feat:`, `fix:`, `refactor:`, `docs:`, `test:`)
- PR titles follow conventional commit style as well

## Adding a New Collector

Collectors are auto-discovered via `BaseCollector.__init_subclass__`. To add one:

1. Add the source name to the `Source` enum in `models.py`
2. Create `src/juris/collectors/mysource.py`:
   ```python
   class MyCollector(BaseCollector):
       source = Source.MY_SOURCE
       supported_doc_types = [DocType.SOME_TYPE]
       preferred_for = [DocType.SOME_TYPE]  # optional — wins when multiple providers exist

       async def collect(self, doc_type, *, session=None, since=None, until=None,
                         limit=None, skip_content=False) -> AsyncIterator[Document]: ...
       async def get_document(self, source_id: str) -> Document | None: ...
   ```
3. No changes needed in `cli.py`, `__init__.py`, or any registry file.

## Important Notes

- When the project structure changes (new files, directories, or significant reorganization), update this CLAUDE.md file to reflect the changes.
- Output format: documents are stored as `data/{doc_type}/{session}/{id}.{json|md}`
- Collection state is tracked in `.state/{source}_{doc_type}.json`
