"""File storage engine: JSON + Markdown dual format."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from juris.models import DocType, Document
from juris.utils import sanitize_filename


def _doc_dir(base_dir: Path, doc_type: DocType, session: str | None) -> Path:
    """Derive the directory for a document type and session."""
    type_dir = base_dir / doc_type.value
    if session:
        # "2024/25" -> "2024-25", plain year stays as-is
        subdir = session.replace("/", "-")
        return type_dir / subdir
    return type_dir


def _doc_path(base_dir: Path, doc: Document, ext: str) -> Path:
    """Full path for a document file."""
    directory = _doc_dir(base_dir, doc.doc_type, doc.session)
    filename = sanitize_filename(doc.doc_id)
    return directory / f"{filename}.{ext}"


def save_document(doc: Document, base_dir: Path) -> Path:
    """Save a document as both JSON and Markdown. Returns the JSON path."""
    json_path = _doc_path(base_dir, doc, "json")
    md_path = _doc_path(base_dir, doc, "md")
    json_path.parent.mkdir(parents=True, exist_ok=True)

    # JSON — full model dump
    data = doc.model_dump(mode="json")
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Markdown — YAML frontmatter + text body
    frontmatter = {
        "doc_id": doc.doc_id,
        "doc_type": doc.doc_type.value,
        "title": doc.title,
        "date": str(doc.date),
        "source": doc.source.value,
    }
    if doc.department:
        frontmatter["department"] = doc.department
    if doc.source_url:
        frontmatter["source_url"] = doc.source_url
    if doc.session:
        frontmatter["session"] = doc.session

    fm_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
    body = doc.text or doc.summary or ""
    type_label = doc.doc_type.value.upper()
    if doc.doc_type == DocType.PROP:
        type_label = "Proposition"
    elif doc.doc_type == DocType.SOU:
        type_label = "SOU"

    designation = f"{type_label} {doc.session}:{doc.designation}" if doc.session else doc.designation

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
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return json_path


def load_document(doc_id: str, doc_type: DocType, session: str | None, base_dir: Path) -> Document | None:
    """Load a document from its JSON file."""
    directory = _doc_dir(base_dir, doc_type, session)
    filename = sanitize_filename(doc_id)
    json_path = directory / f"{filename}.json"
    if not json_path.exists():
        return None
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return Document.model_validate(data)


def document_exists(doc_id: str, doc_type: DocType, session: str | None, base_dir: Path) -> bool:
    """Check if a document has already been saved."""
    directory = _doc_dir(base_dir, doc_type, session)
    filename = sanitize_filename(doc_id)
    return (directory / f"{filename}.json").exists()
