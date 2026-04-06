"""File storage engine: JSON + Markdown dual format."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from juris.models import DocType, Document
from juris.utils import sanitize_filename

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
        designation = doc.designation

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
