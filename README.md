# juris

[![Website](https://img.shields.io/badge/website-juris-d4a843?style=flat&logo=github)](https://niclaslindstedt.github.io/juris/)

### Swedish Parliament
[![prop](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-prop.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-prop.yml)
[![mot](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-mot.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-mot.yml)
[![bet](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-bet.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-bet.yml)
[![skr](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-skr.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-skr.yml)

### Swedish Government
[![sou](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-sou.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-sou.yml)
[![ds](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-ds.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-ds.yml)
[![dir](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-dir.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-dir.yml)
[![lagr](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-lagr.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-lagr.yml)
[![sfs](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-sfs.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-sfs.yml)

### Courts
[![nja](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-nja.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-nja.yml)
[![ad](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-ad.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-ad.yml)
[![hfd](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-hfd.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-hfd.yml)
[![mod](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-mod.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-mod.yml)
[![pmod](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-pmod.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-pmod.yml)

### Authorities
[![jo](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-jo.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-jo.yml)
[![jk](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-jk.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-jk.yml)
[![foreskrift](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-foreskrift.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-foreskrift.yml)

### EU Law
[![eu_reg](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-eu_reg.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-eu_reg.yml)
[![eu_dir](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-eu_dir.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-eu_dir.yml)
[![cjeu](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-cjeu.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-cjeu.yml)
[![echr](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-echr.yml/badge.svg)](https://github.com/niclaslindstedt/juris/actions/workflows/e2e-echr.yml)

A command-line tool for collecting and normalizing Swedish legal documents from official government sources.

Sweden has a wealth of public legal information — laws, government bills, public inquiries, court decisions — scattered across multiple government websites and APIs with inconsistent formats. **juris** collects documents from these sources, normalizes them into a unified format, and saves them as browsable, version-controlled files (Markdown + JSON). Think of it as a git-native open database for Swedish law.

## Features

- **8 data sources** covering Swedish parliament, government, courts, authorities, and EU law
- **21 document types** from bills and motions to court decisions and EU regulations
- **Dual output format** — Markdown (human-readable, browsable on GitHub) and JSON (machine-parseable)
- **Incremental collection** with state tracking to resume where you left off
- **Async I/O** with built-in rate limiting to respect source servers
- **PDF text extraction** from document attachments
- **Date and session filtering** for targeted collection

## Data sources

| Source | Method | Document types |
|--------|--------|----------------|
| [Riksdagen](https://data.riksdagen.se/) | JSON API | prop, sou, mot, bet, dir, skr, sfs |
| [Regeringen.se](https://www.regeringen.se/rattsdokument/) | Web scraping | prop, sou, ds, lagr, dir, skr |
| [Domstolsverket](https://rattspraxis.etjanst.domstol.se/) | REST API | nja, ad, hfd, mod, pmod |
| [JO](https://www.jo.se/) | Web scraping | jo |
| [JK](https://www.jk.se/) | Web scraping | jk |
| [Lagrummet](https://lagrummet.se/) | Web scraping | foreskrift |
| [EUR-Lex](https://eur-lex.europa.eu/) | SPARQL | eu_reg, eu_dir |
| [CURIA / HUDOC](https://curia.europa.eu/) | SPARQL / JSON API | cjeu, echr |

## Document types

### Swedish Parliament

| Type | Swedish | English |
|------|---------|---------|
| `prop` | Propositioner | Government bills |
| `mot` | Motioner | Parliamentary motions |
| `bet` | Betänkanden | Committee reports |
| `skr` | Skrivelser | Government communications |

### Swedish Government

| Type | Swedish | English |
|------|---------|---------|
| `sou` | Statens offentliga utredningar | State public inquiries |
| `ds` | Departementsserien | Department series |
| `dir` | Kommittédirektiv | Committee directives |
| `lagr` | Lagrådsremisser | Legal council referrals |
| `sfs` | Svensk författningssamling | Swedish Code of Statutes |

### Courts

| Type | Swedish | English |
|------|---------|---------|
| `nja` | Nytt Juridiskt Arkiv | Supreme Court precedents |
| `ad` | Arbetsdomstolens domar | Labour Court decisions |
| `hfd` | Högsta förvaltningsdomstolens årsbok | Supreme Administrative Court |
| `mod` | Mark- och miljööverdomstolen | Land and Environment Court |
| `pmod` | Patent- och marknadsöverdomstolen | Patent and Market Court |

### Authorities

| Type | Swedish | English |
|------|---------|---------|
| `jo` | Justitieombudsmannens beslut | Parliamentary Ombudsman decisions |
| `jk` | Justitiekanslerns beslut | Chancellor of Justice decisions |
| `foreskrift` | Myndighetsföreskrifter | Agency regulations |

### EU law

| Type | Swedish | English |
|------|---------|---------|
| `eu_reg` | EU-förordningar | EU regulations |
| `eu_dir` | EU-direktiv | EU directives |
| `cjeu` | EU-domstolens domar | Court of Justice of the EU |
| `echr` | Europadomstolens domar | European Court of Human Rights |

## Installation

```bash
pip install -e .
```

Requires Python 3.11 or later.

## Usage

```bash
# Collect government bills from the 2024/25 parliamentary session
juris collect riksdagen --type prop --session 2024/25

# Collect SOU reports published since a specific date
juris collect riksdagen --type sou --since 2024-01-01

# Collect from the government website with a limit
juris collect regeringen --type prop --session 2024/25 --limit 5

# Collect Supreme Court decisions
juris collect domstol --type nja --since 2024-01-01

# Collect agency regulations
juris collect lagrummet --type foreskrift --limit 10

# Collect EU regulations
juris collect eur_lex --type eu_reg --since 2024-01-01

# Check collection progress
juris status

# Count collected documents
juris stats
```

### Options

| Option | Description |
|--------|-------------|
| `--type TYPE` | Document type to collect (required) |
| `--session SESSION` | Parliamentary session, e.g. `2024/25` |
| `--since DATE` | Collect documents from this date (YYYY-MM-DD) |
| `--until DATE` | Collect documents until this date (YYYY-MM-DD) |
| `--limit N` | Maximum number of documents to collect |
| `--skip-existing / --no-skip-existing` | Skip already collected documents (default: on) |
| `--skip-content / --no-skip-content` | Metadata only, skip full text (default: off) |
| `--data-dir PATH` | Output directory (default: `data`) |
| `-v, --verbose` | Enable debug logging |

## Output format

Each document is saved in two formats:

**Markdown** (human-readable, browsable on GitHub):

```markdown
---
doc_id: "prop-2024/25:208"
doc_type: prop
title: "Ett mer heltäckande straffansvar vid angrepp på företagshemligheter"
date: "2025-09-08"
source: riksdagen
department: Justitiedepartementet
session: "2024/25"
source_url: "https://..."
---

# Ett mer heltäckande straffansvar vid angrepp på företagshemligheter

Proposition 2024/25:208

[full text...]
```

**JSON** (machine-readable, full metadata):

```json
{
  "doc_id": "prop-2024/25:208",
  "doc_type": "prop",
  "title": "Ett mer heltäckande straffansvar...",
  "date": "2025-09-08",
  "text": "...",
  "source": "riksdagen",
  "attachments": [...]
}
```

Documents are organized by type and session:

```
data/
├── prop/
│   └── 2024-25/
│       ├── prop-2024-25_208.json
│       └── prop-2024-25_208.md
├── sou/
│   └── 2024/
├── nja/
└── .state/
```

## Project structure

```
src/juris/
├── cli.py              # Command-line interface (Click)
├── models.py           # Document data models (Pydantic)
├── storage.py          # File storage (JSON + Markdown)
├── state.py            # Incremental collection state
├── pdf.py              # PDF text extraction
├── utils.py            # Shared utilities
└── collectors/
    ├── base.py         # Abstract base collector
    ├── riksdagen.py    # Riksdagen API
    ├── regeringen.py   # Regeringen.se scraper
    ├── domstol.py      # Court decisions API
    ├── jo_jk.py        # JO/JK decisions
    ├── lagrummet.py    # Agency regulations
    ├── eurlex.py       # EUR-Lex SPARQL
    ├── curia.py        # CJEU SPARQL
    └── hudoc.py        # ECtHR API
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Lint
ruff check src/

# Type check
mypy src/
```

## License

MIT
