# Overview

## What is juris?

juris is a command-line tool that collects Swedish legal documents from public
data sources and stores them locally in a unified, git-friendly format. It
bridges the gap between scattered government APIs and a structured local
archive that is easy to search, version, and process.

## The Problem

Swedish legal data is spread across multiple government websites and APIs,
each with its own format, access method, and quirks:

- The Riksdagen (parliament) publishes propositions and motions via a JSON API
- The government website (regeringen.se) requires web scraping
- Court decisions come from a separate REST API
- EU legal documents are accessed through SPARQL endpoints
- Ombudsman decisions are scraped from individual websites

These sources return data in incompatible formats — JSON, HTML, XML, PDF —
with different field names, date formats, and identification schemes. Building
any application on top of this data requires solving the same normalization
problem over and over.

## The Solution

juris provides a single CLI that connects to all 8 sources and normalizes
every document into a common `Document` model. Each document is saved as
both JSON (for programmatic access) and Markdown with YAML frontmatter
(for human reading and git diffs).

The result is a local directory tree like:

```
data/
├── prop/
│   └── 2024-25/
│       ├── prop-2024-25_208.json
│       └── prop-2024-25_208.md
├── sou/
│   └── 2024/
│       ├── sou-2024_42.json
│       └── sou-2024_42.md
├── nja/
│   └── 2025/
│       ├── nja-2025_19.json
│       └── nja-2025_19.md
└── ...
```

## Key Capabilities

### 8 Data Sources

juris connects to the Swedish Parliament, Government, courts, ombudsmen,
regulatory agencies, EUR-Lex, the CJEU, and the European Court of Human
Rights.

### 21 Document Types

Coverage spans parliamentary documents (propositions, motions, committee
reports), government publications (SOU, Ds, directives), court decisions
(Supreme Court, Labour Court, administrative courts), ombudsman rulings
(JO, JK), agency regulations, and EU/ECHR case law.

### Incremental Collection

juris tracks what has already been collected and only fetches new documents
on subsequent runs. Collection state is stored per source and document type,
so you can resume interrupted runs without re-downloading.

### Dual Output Format

Every document is saved as both a full JSON file (all model fields) and a
Markdown file with YAML frontmatter (metadata headers plus extracted text).
The Markdown format is designed for readability and clean git diffs.

### Smart Provider Selection

When a document type is available from multiple sources (e.g., propositions
from both Riksdagen and Regeringen), juris automatically selects the
preferred provider — the one with the most complete and structured data.
You can override this and collect from all providers if needed.

### Robust HTTP Handling

All HTTP requests use exponential backoff with retry on transient errors
(429, 5xx, timeouts). Rate limiting is enforced per source to respect
API guidelines. PDF attachments are downloaded and their text extracted
automatically.

## Use Cases

- **Legal research**: Build a searchable archive of Swedish legal documents
- **Data analysis**: Analyze trends in legislation, court decisions, or
  regulatory changes
- **NLP/AI training**: Collect structured legal text for language model
  training or legal AI applications
- **Monitoring**: Track new publications from specific sources or document
  types with incremental collection
- **Archival**: Maintain a local, version-controlled mirror of public legal
  data

## Quick Start

Install juris and collect your first documents:

```sh
pip install juris
juris collect riksdagen --type prop --session 2024/25 --limit 5
juris stats
```

See the [README](../README.md) for detailed setup instructions, or
jump to the [architecture](architecture) guide to understand how juris works
under the hood.
