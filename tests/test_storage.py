"""Tests for document storage roundtrip fidelity."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from juris.models import Attachment, DocType, Document, Source
from juris.storage import document_exists, load_document, save_document


class TestStorageRoundtrip:
    def test_save_and_load(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        doc = Document(
            doc_id="prop-2024/25:208",
            doc_type=DocType.PROP,
            designation="208",
            session="2024/25",
            title="En proposition om något viktigt",
            summary="Sammanfattning av propositionen.",
            text="Full text of the proposition.",
            date=date(2025, 3, 15),
            department="Justitiedepartementet",
            source=Source.RIKSDAGEN,
            source_id="HC03208",
            source_url="https://data.riksdagen.se/dokument/HC03208",
            fetched_at=datetime.now(tz=UTC),
        )

        json_path = save_document(doc, data_dir)
        assert json_path.exists()
        assert json_path.suffix == ".json"

        # Markdown file should also exist
        md_path = json_path.with_suffix(".md")
        assert md_path.exists()

        loaded = load_document(doc.doc_id, doc.doc_type, doc.session, data_dir)
        assert loaded is not None
        assert loaded.doc_id == doc.doc_id
        assert loaded.doc_type == doc.doc_type
        assert loaded.designation == doc.designation
        assert loaded.session == doc.session
        assert loaded.title == doc.title
        assert loaded.summary == doc.summary
        assert loaded.text == doc.text
        assert loaded.date == doc.date
        assert loaded.department == doc.department
        assert loaded.source == doc.source
        assert loaded.source_id == doc.source_id
        assert loaded.source_url == doc.source_url

    def test_document_exists(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        assert not document_exists("prop-2024/25:208", DocType.PROP, "2024/25", data_dir)

        doc = Document(
            doc_id="prop-2024/25:208",
            doc_type=DocType.PROP,
            designation="208",
            session="2024/25",
            title="Test",
            date=date(2025, 1, 1),
            source=Source.RIKSDAGEN,
            fetched_at=datetime.now(tz=UTC),
        )
        save_document(doc, data_dir)

        assert document_exists("prop-2024/25:208", DocType.PROP, "2024/25", data_dir)

    def test_roundtrip_with_attachments(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        doc = Document(
            doc_id="sou-2024:42",
            doc_type=DocType.SOU,
            designation="42",
            session="2024",
            title="SOU with attachment",
            date=date(2024, 6, 1),
            source=Source.RIKSDAGEN,
            fetched_at=datetime.now(tz=UTC),
            attachments=[
                Attachment(
                    filename="sou-2024_42.pdf",
                    url="https://example.com/sou.pdf",
                    mime_type="application/pdf",
                    size=1024,
                )
            ],
        )

        save_document(doc, data_dir)
        loaded = load_document(doc.doc_id, doc.doc_type, doc.session, data_dir)
        assert loaded is not None
        assert len(loaded.attachments) == 1
        assert loaded.attachments[0].filename == "sou-2024_42.pdf"
        assert loaded.attachments[0].mime_type == "application/pdf"

    def test_roundtrip_minimal_doc(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        doc = Document(
            doc_id="echr-12345/20",
            doc_type=DocType.ECHR,
            designation="12345/20",
            title="Case of X v. Sweden",
            date=date(2023, 6, 1),
            source=Source.HUDOC,
            fetched_at=datetime.now(tz=UTC),
        )

        save_document(doc, data_dir)
        loaded = load_document(doc.doc_id, doc.doc_type, doc.session, data_dir)
        assert loaded is not None
        assert loaded.doc_id == "echr-12345/20"
        assert loaded.session is None
        assert loaded.text is None
        assert loaded.html is None
        assert loaded.attachments == []
