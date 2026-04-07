# Storage Format

## Overview

juris saves every collected document in two formats simultaneously:
**JSON** for complete structured data and **Markdown** for human-readable
content with metadata. Both files are written to the same directory,
organized by document type and session.

## Directory Layout

```
data/
├── prop/
│   └── 2024-25/
│       ├── prop-2024-25_208.json
│       ├── prop-2024-25_208.md
│       └── attachments/
│           └── prop-2024-25_208.pdf
├── sou/
│   └── 2024/
│       ├── sou-2024_42.json
│       └── sou-2024_42.md
├── nja/
│   └── 2025/
│       ├── nja-2025_19.json
│       ├── nja-2025_19.md
│       └── attachments/
│           └── nja-2025_19.pdf
└── .state/
    ├── riksdagen_prop.json
    ├── domstol_nja.json
    └── ...
```

### Path Construction

Document paths follow this pattern:

```
{data_dir}/{doc_type}/{session}/{sanitized_doc_id}.{json,md}
```

- **data_dir**: Configurable via `--data-dir`, defaults to `data`
- **doc_type**: The document type value (e.g., `prop`, `sou`, `nja`)
- **session**: The session or year, with `/` replaced by `-` for
  filesystem safety (e.g., `2024/25` → `2024-25`)
- **sanitized_doc_id**: The doc_id with `/` → `-`, `:` → `_`, ` ` → `-`

Attachments are stored in an `attachments/` subdirectory within the
same session directory.

## JSON Format

The JSON file contains a complete dump of the `Document` Pydantic model.
Every field is preserved, including `html`, `attachments`, and metadata
that does not render well in plain text.

Example:

```json
{
  "doc_id": "prop-2024/25:208",
  "doc_type": "prop",
  "designation": "208",
  "session": "2024/25",
  "title": "En förnyad satisfaktionslag",
  "summary": "I denna proposition föreslår regeringen...",
  "text": "En förnyad satisfaktionslag\n\nI denna proposition...",
  "html": null,
  "date": "2025-03-15",
  "department": "Justitiedepartementet",
  "committee": null,
  "status": null,
  "source": "riksdagen",
  "source_id": "HC03208",
  "source_url": "https://data.riksdagen.se/dokument/HC03208",
  "fetched_at": "2025-06-01T10:30:00",
  "attachments": [
    {
      "filename": "prop-2024-25_208.pdf",
      "url": "https://data.riksdagen.se/fil/ABC123",
      "mime_type": "application/pdf",
      "size": 1048576,
      "local_path": "data/prop/2024-25/attachments/prop-2024-25_208.pdf"
    }
  ]
}
```

## Markdown Format

The Markdown file consists of YAML frontmatter (metadata) followed by
the document's extracted text content. This format is designed for:

- **Human reading**: Open in any text editor or Markdown viewer
- **Git diffs**: Changes to metadata and text produce clean, readable diffs
- **Static site generation**: Compatible with Jekyll, Hugo, and similar tools

Example:

```markdown
---
doc_id: prop-2024/25:208
doc_type: prop
designation: "208"
session: 2024/25
title: En förnyad satisfaktionslag
date: 2025-03-15
department: Justitiedepartementet
source: riksdagen
source_id: HC03208
source_url: https://data.riksdagen.se/dokument/HC03208
fetched_at: 2025-06-01T10:30:00
---

En förnyad satisfaktionslag

I denna proposition föreslår regeringen...
```

### Frontmatter Fields

The YAML frontmatter includes the document's metadata fields. Fields
with `null` values are omitted to keep the frontmatter clean. The `text`,
`html`, and `attachments` fields are excluded from frontmatter — the
text becomes the Markdown body, and HTML/attachments are only available
in the JSON file.

## State Tracking

Collection state is stored separately from document data, in the
`.state/` directory under the data directory:

```
{data_dir}/.state/{source}_{doc_type}.json
```

Each state file tracks the progress of one (source, doc_type) collection:

```json
{
  "source": "riksdagen",
  "doc_type": "prop",
  "last_fetched_date": "2025-06-01",
  "last_page": 3,
  "total_collected": 47,
  "last_run_at": "2025-06-01T10:45:00"
}
```

### State Fields

| Field | Description |
|---|---|
| `source` | The collector source name |
| `doc_type` | The document type being collected |
| `last_fetched_date` | ISO date of the newest document seen |
| `last_page` | Pagination checkpoint (page number or offset) |
| `total_collected` | Running count of documents collected |
| `last_run_at` | ISO datetime of the last collection run |

### Incremental Behavior

When you run a collection command, the pipeline checks the state file
for the relevant (source, doc_type) pair:

1. If no state exists, collection starts from scratch
2. If state exists, `last_fetched_date` is used as the `since` parameter
   to skip already-collected time ranges
3. After the run completes, the state is updated with the new counts
   and timestamp

Additionally, the pipeline checks `document_exists()` before saving
each document, skipping any that are already on disk. This double-check
prevents duplicates even when date-based filtering is imprecise.

## Storage Functions

The `storage.py` module provides four key functions:

**`save_document(doc, data_dir)`** — Writes both JSON and Markdown files.
Creates directories as needed. Returns the JSON file path.

**`load_document(path)`** — Reads a JSON file and returns a `Document`
instance.

**`document_exists(doc_id, doc_type, session, data_dir)`** — Checks
whether a document has already been saved by looking for its JSON file.
Used by the pipeline to skip duplicates.

**`_doc_dir(doc_type, session, data_dir)`** — Computes the directory path
for a given document type and session. Internal helper used by the other
functions.
