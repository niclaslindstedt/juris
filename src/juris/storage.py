"""File storage engine: JSON + Markdown dual format."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from juris.models import DocType, Document
from juris.utils import atomic_write_text, sanitize_filename

# Human-readable Swedish labels for document types (used in Markdown output)
_TYPE_LABELS: dict[DocType, str] = {
    DocType.PROP: "Proposition",
    DocType.SOU: "SOU",
    DocType.MOT: "Motion",
    DocType.BET: "Betänkande",
    DocType.DS: "Ds",
    DocType.LAGR: "Lagrådsremiss",
    DocType.DIR: "Kommittédirektiv",
    DocType.SKR: "Skrivelse",
    DocType.SFS: "SFS",
    DocType.NJA: "NJA",
    DocType.AD: "AD",
    DocType.HFD: "HFD",
    DocType.MOD: "MÖD",
    DocType.PMOD: "PMÖD",
    DocType.JO: "JO",
    DocType.JK: "JK",
    DocType.FORESKRIFT: "Föreskrift",
    DocType.EU_REG: "EU-förordning",
    DocType.EU_DIR: "EU-direktiv",
    DocType.CJEU: "EU-domstolen",
    DocType.ECHR: "Europadomstolen",
}


def doc_dir(base_dir: Path, doc_type: DocType, session: str | None) -> Path:
    """Derive the directory for a document type and session."""
    type_dir = base_dir / doc_type.value
    if session:
        # "2024/25" -> "2024-25", plain year stays as-is
        subdir = session.replace("/", "-")
        return type_dir / subdir
    return type_dir


def _doc_path(base_dir: Path, doc: Document, ext: str) -> Path:
    """Full path for a document file."""
    directory = doc_dir(base_dir, doc.doc_type, doc.session)
    filename = sanitize_filename(doc.doc_id)
    return directory / f"{filename}.{ext}"


def save_document(doc: Document, base_dir: Path) -> Path:
    """Save a document as both JSON and Markdown. Returns the JSON path."""
    json_path = _doc_path(base_dir, doc, "json")
    md_path = _doc_path(base_dir, doc, "md")
    # JSON — full model dump
    data = doc.model_dump(mode="json")
    atomic_write_text(json_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    # Markdown — YAML frontmatter + text body
    frontmatter: dict[str, str | int] = {
        "doc_id": doc.doc_id,
        "doc_type": doc.doc_type.value,
        "title": doc.title,
        "designation": doc.designation,
        "date": str(doc.date),
        "source": doc.source.value,
    }
    if doc.session:
        frontmatter["session"] = doc.session
    if doc.department:
        frontmatter["department"] = doc.department
    if doc.committee:
        frontmatter["committee"] = doc.committee
    if doc.summary:
        frontmatter["summary"] = doc.summary[:200]
    if doc.source_url:
        frontmatter["source_url"] = doc.source_url
    if doc.text:
        frontmatter["text_length"] = len(doc.text)

    fm_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
    body = doc.text or doc.summary or ""
    type_label = _TYPE_LABELS.get(doc.doc_type, doc.doc_type.value.upper())

    if doc.session:
        designation = f"{type_label} {doc.session}:{doc.designation}"
    else:
        designation = f"{type_label} {doc.designation}"

    lines = [
        "---",
        fm_str.rstrip(),
        "---",
        "",
        f"# {doc.title}",
        "",
        designation,
        "",
        body,
        "",
    ]
    atomic_write_text(md_path, "\n".join(lines))

    return json_path


def load_document(
    doc_id: str,
    doc_type: DocType,
    session: str | None,
    base_dir: Path,
) -> Document | None:
    """Load a document from its JSON file."""
    directory = doc_dir(base_dir, doc_type, session)
    filename = sanitize_filename(doc_id)
    json_path = directory / f"{filename}.json"
    if not json_path.exists():
        return None
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return Document.model_validate(data)


def document_exists(doc_id: str, doc_type: DocType, session: str | None, base_dir: Path) -> bool:
    """Check if a document has already been saved."""
    directory = doc_dir(base_dir, doc_type, session)
    filename = sanitize_filename(doc_id)
    return (directory / f"{filename}.json").exists()


def document_valid(
    doc_id: str,
    doc_type: DocType,
    session: str | None,
    base_dir: Path,
) -> bool:
    """Deeper integrity check before skipping a document.

    Returns True only when:
      - the JSON file exists and parses into a :class:`Document`
      - the companion ``.md`` file exists
      - every attachment with a recorded ``local_path`` is present and non-empty

    Any failure returns False so the caller can re-fetch.
    """
    directory = doc_dir(base_dir, doc_type, session)
    filename = sanitize_filename(doc_id)
    json_path = directory / f"{filename}.json"
    md_path = directory / f"{filename}.md"
    if not json_path.exists() or not md_path.exists():
        return False
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        doc = Document.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        return False
    for att in doc.attachments:
        if not att.local_path:
            continue
        att_path = base_dir / att.local_path
        try:
            if not att_path.exists() or att_path.stat().st_size == 0:
                return False
        except OSError:
            return False
    return True
