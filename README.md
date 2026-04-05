# juris

A tool for collecting, normalizing, and openly sharing Swedish legal data.

## Goals

Sweden has a wealth of public legal information — laws, government bills, public inquiries, committee reports — spread across multiple government websites and APIs. **juris** aims to:

1. **Collect** legal documents from official Swedish sources into a single, consistent dataset
2. **Normalize** documents into a unified format with clean metadata, regardless of source
3. **Open-source the data** as browsable, version-controlled files that anyone can use, fork, and build upon

The collected dataset is stored as Markdown files (with YAML frontmatter) and JSON — human-readable on GitHub, machine-parseable for downstream tools. Think of it as a git-native open database for Swedish law.

### What this enables

By providing clean, structured, openly licensed legal data, juris can serve as a foundation for:

- AI-powered legal research tools (RAG, vector databases, MCP servers)
- Legal search engines and APIs
- Academic research on Swedish legislation
- Civic tech projects that make law more accessible

## Document types

| Type | Swedish | Description |
|------|---------|-------------|
| `prop` | Propositioner | Government bills |
| `sou` | Statens offentliga utredningar | State public inquiries |
| `mot` | Motioner | Parliamentary motions |
| `bet` | Betänkanden | Committee reports |
| `ds` | Departementsserien | Department series |
| `dir` | Kommittédirektiv | Committee directives |
| `skr` | Skrivelser | Government communications |
| `lagr` | Lagrådsremisser | Legal council referrals |

## Data sources

| Source | Type | Status |
|--------|------|--------|
| [Riksdagen API](https://data.riksdagen.se/) | JSON API | Implemented |
| [Regeringen.se](https://www.regeringen.se/rattsdokument/) | Web scraping | Planned |
| [Lagrummet.se](https://lagrummet.se/) | RDF/Atom feeds | Planned |

The strategy is **APIs first, scrape only for gaps** — we prefer structured data where available.

## Usage

```bash
# Install
pip install -e .

# Collect propositioner from the 2024/25 parliamentary session
juris collect riksdagen --type prop --session 2024/25

# Collect SOU reports from a date range
juris collect riksdagen --type sou --since 2024-01-01

# Limit collection (useful for testing)
juris collect riksdagen --type prop --session 2024/25 --limit 5

# Check collection progress
juris status

# Count collected documents
juris stats
```

## File format

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

## Requirements

- Python 3.11+

## License

MIT
