# Contributing to juris

Thank you for your interest in contributing to juris! This guide will help you get started.

## Getting Started

### Prerequisites

- Python 3.11 or later
- Git

### Setup

```bash
git clone https://github.com/niclaslindstedt/juris.git
cd juris
make install
```

This creates a virtual environment in `.venv/` and installs the package with dev dependencies.

## Development Workflow

1. Fork and clone the repository
2. Create a feature branch from `main`
3. Make your changes
4. Run the checks:

```bash
make lint        # Lint + format check
make typecheck   # Type check (strict mode)
make test        # Unit tests
```

To auto-format code:

```bash
make format
```

To run end-to-end tests (these hit live APIs and are slow):

```bash
make test-e2e
```

## Coding Standards

- **Line length:** 100 characters
- **Linter:** ruff with rules E, F, I, W
- **Type checker:** mypy in strict mode
- **Indentation:** 4 spaces for Python, 2 spaces for TypeScript/YAML
- **Async:** All collectors use async/await with httpx

## Commit Conventions

This project uses [conventional commits](https://www.conventionalcommits.org/). All commit messages and PR titles must follow this format:

- `feat:` — new feature
- `fix:` — bug fix
- `refactor:` — code restructuring without behavior change
- `docs:` — documentation changes
- `test:` — test additions or changes
- `perf:` — performance improvements
- `chore:` — maintenance tasks

Examples:

```
feat: add support for new document type
fix: handle empty response from riksdagen API
docs: update collector documentation
```

## Adding a New Collector

Collectors are auto-discovered via `BaseCollector.__init_subclass__`. No registration step is needed.

1. Add the source name to the `Source` enum in `src/juris/models.py`
2. Create `src/juris/collectors/mysource.py`:

```python
class MyCollector(BaseCollector):
    source = Source.MY_SOURCE
    supported_doc_types = [DocType.SOME_TYPE]

    async def collect(self, doc_type, *, session=None, since=None, until=None,
                      limit=None, skip_content=False) -> AsyncIterator[Document]:
        ...

    async def get_document(self, source_id: str) -> Document | None:
        ...
```

3. That's it — the CLI and pipeline will pick it up automatically.

## Adding a New Document Type

1. Add the type to the `DocType` enum in `src/juris/models.py`
2. Add it to the relevant collector's `supported_doc_types` list
3. Add parsing logic in the collector's `collect` method

## Pull Request Process

1. Ensure your PR title follows conventional commit format
2. All CI checks must pass:
   - Linting (ruff check + format)
   - Type checking (mypy strict)
   - Unit tests (Python 3.11, 3.12, 3.13)
3. Update documentation if your change affects the public API or project structure
4. Update `CLAUDE.md` if the project structure changes

## Reporting Issues

- **Bugs:** Use the [bug report template](https://github.com/niclaslindstedt/juris/issues/new?template=bug_report.md)
- **Feature requests:** Use the [feature request template](https://github.com/niclaslindstedt/juris/issues/new?template=feature_request.md)
- **Security vulnerabilities:** See [SECURITY.md](SECURITY.md)

## Code of Conduct

This project follows the [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you are expected to uphold this code.

## License

By contributing to juris, you agree that your contributions will be licensed under the [MIT License](LICENSE).
