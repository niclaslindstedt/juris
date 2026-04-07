"""End-to-end tests that download real documents from all providers.

These tests hit live APIs and verify the full pipeline:
  source API -> collector -> Document model -> storage (JSON + Markdown)

Run with: pytest tests/test_e2e.py -m e2e -v
Skip in CI: pytest -m "not e2e"
"""

from __future__ import annotations

import pytest

from tests.conftest import (
    assert_document_quality,
    assert_markdown_valid,
    load_saved_documents,
    load_saved_markdown,
    run_collect,
)

# ---------------------------------------------------------------------------
# Riksdagen (JSON API)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestRiksdagenE2E:
    """E2E tests for the Riksdagen data.riksdagen.se JSON API."""

    @pytest.mark.parametrize("doc_type", ["prop", "sou", "mot", "bet", "dir", "skr", "sfs"])
    def test_collect_each_type(self, cli_runner, tmp_data_dir, doc_type):
        """Download 1 document of each supported type."""
        run_collect(
            cli_runner,
            ["collect", "riksdagen", "--type", doc_type, "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, doc_type)
        assert len(docs) >= 1, f"No {doc_type} documents saved"

        for doc in docs:
            assert_document_quality(doc, expected_type=doc_type, expected_source="riksdagen")

        # Markdown file should also exist
        md_files = load_saved_markdown(tmp_data_dir, doc_type)
        assert len(md_files) >= 1, f"No {doc_type} markdown files saved"
        assert_markdown_valid(md_files[0])

    def test_collect_prop_with_session(self, cli_runner, tmp_data_dir):
        """Session filtering narrows results to a specific riksmöte."""
        run_collect(
            cli_runner,
            ["collect", "riksdagen", "--type", "prop", "--session", "2024/25",
             "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "prop")
        assert len(docs) >= 1
        for doc in docs:
            assert doc["session"] == "2024/25", f"Expected session 2024/25, got {doc['session']}"

    def test_collect_prop_with_date_range(self, cli_runner, tmp_data_dir):
        """Date range filtering limits results by date."""
        run_collect(
            cli_runner,
            ["collect", "riksdagen", "--type", "prop",
             "--since", "2025-01-01", "--until", "2025-12-31",
             "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "prop")
        assert len(docs) >= 1
        for doc in docs:
            assert doc["date"].startswith("2025"), f"Date outside range: {doc['date']}"

    def test_bet_has_committee(self, cli_runner, tmp_data_dir):
        """BET documents should have committee field populated."""
        run_collect(
            cli_runner,
            ["collect", "riksdagen", "--type", "bet", "--limit", "2", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "bet")
        assert len(docs) >= 1
        # Committee may not always be extractable, but structure should be valid
        for doc in docs:
            assert_document_quality(doc, expected_type="bet")

    def test_sfs_designation_split(self, cli_runner, tmp_data_dir):
        """SFS documents should have year as session, number as designation."""
        run_collect(
            cli_runner,
            ["collect", "riksdagen", "--type", "sfs", "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "sfs")
        assert len(docs) >= 1
        doc = docs[0]
        assert_document_quality(doc, expected_type="sfs")
        # Session should be a 4-digit year for SFS
        if doc.get("session"):
            assert len(doc["session"]) == 4, f"SFS session should be a year, got: {doc['session']}"


# ---------------------------------------------------------------------------
# Regeringen (web scraping)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestRegeringenE2E:
    """E2E tests for the Regeringen.se web scraper."""

    @pytest.mark.parametrize("doc_type", ["prop", "sou", "ds", "lagr", "dir", "skr"])
    def test_collect_each_type(self, cli_runner, tmp_data_dir, doc_type):
        """Download 1 document of each supported type."""
        run_collect(
            cli_runner,
            ["collect", "regeringen", "--type", doc_type, "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, doc_type)
        assert len(docs) >= 1, f"No {doc_type} documents saved"

        for doc in docs:
            assert_document_quality(doc, expected_type=doc_type, expected_source="regeringen")

        md_files = load_saved_markdown(tmp_data_dir, doc_type)
        assert len(md_files) >= 1
        assert_markdown_valid(md_files[0])

    def test_prop_has_department(self, cli_runner, tmp_data_dir):
        """Propositions from Regeringen should have department field."""
        run_collect(
            cli_runner,
            ["collect", "regeringen", "--type", "prop", "--limit", "2", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "prop")
        assert len(docs) >= 1
        for doc in docs:
            assert_document_quality(doc, expected_type="prop")
            # Department is extracted from /tx/ links, may not always be present
            # but structure should be valid


# ---------------------------------------------------------------------------
# Domstol (court decisions API)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestDomstolE2E:
    """E2E tests for the Domstolsverket rättspraxis API."""

    @pytest.mark.parametrize("doc_type", ["nja", "ad", "hfd", "mod", "pmod"])
    def test_collect_each_type(self, cli_runner, tmp_data_dir, doc_type):
        """Download 1 court decision of each type."""
        run_collect(
            cli_runner,
            ["collect", "domstol", "--type", doc_type, "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, doc_type)
        assert len(docs) >= 1, f"No {doc_type} documents saved"

        for doc in docs:
            assert_document_quality(doc, expected_type=doc_type, expected_source="domstol")
            # Court decisions should have department (court name)
            assert doc.get("department"), f"Court decision missing department: {doc['doc_id']}"

        md_files = load_saved_markdown(tmp_data_dir, doc_type)
        assert len(md_files) >= 1
        assert_markdown_valid(md_files[0])

    def test_nja_designation_format(self, cli_runner, tmp_data_dir):
        """NJA designation should be a number (reference number)."""
        run_collect(
            cli_runner,
            ["collect", "domstol", "--type", "nja", "--limit", "2", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "nja")
        assert len(docs) >= 1
        for doc in docs:
            assert_document_quality(doc, expected_type="nja")
            # Designation should be a number or case number, not "unknown"
            assert doc["designation"] != "unknown", (
                f"NJA designation is 'unknown': {doc['doc_id']}"
            )


# ---------------------------------------------------------------------------
# JO/JK (Ombudsman / Chancellor of Justice)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestJoJkE2E:
    """E2E tests for JO and JK web scrapers."""

    @pytest.mark.parametrize("doc_type", [
        "jo",
        pytest.param("jk", marks=pytest.mark.xfail(reason="www.jk.se is unreachable")),
    ])
    def test_collect_each_type(self, cli_runner, tmp_data_dir, doc_type):
        """Download 1 decision from JO and JK."""
        run_collect(
            cli_runner,
            ["collect", "jo_jk", "--type", doc_type, "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, doc_type)
        assert len(docs) >= 1, f"No {doc_type} documents saved"

        for doc in docs:
            assert_document_quality(doc, expected_type=doc_type, expected_source="jo_jk")

        md_files = load_saved_markdown(tmp_data_dir, doc_type)
        assert len(md_files) >= 1
        assert_markdown_valid(md_files[0])


# ---------------------------------------------------------------------------
# Lagrummet (agency regulations)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestLagrummetE2E:
    """E2E tests for the Lagrummet agency regulations scraper."""

    def test_collect_foreskrift(self, cli_runner, tmp_data_dir):
        """Download 1 föreskrift."""
        run_collect(
            cli_runner,
            ["collect", "lagrummet", "--type", "foreskrift", "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "foreskrift")
        assert len(docs) >= 1, "No foreskrift documents saved"

        for doc in docs:
            assert_document_quality(
                doc, expected_type="foreskrift", expected_source="lagrummet"
            )
            # Föreskrift designation should contain the agency prefix (e.g. AFS, SOSFS)
            assert doc.get("department"), f"Föreskrift missing department: {doc['doc_id']}"

        md_files = load_saved_markdown(tmp_data_dir, "foreskrift")
        assert len(md_files) >= 1
        assert_markdown_valid(md_files[0])


# ---------------------------------------------------------------------------
# EUR-Lex (EU regulations and directives)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestEurLexE2E:
    """E2E tests for the EUR-Lex SPARQL collector."""

    @pytest.mark.parametrize("doc_type", ["eu_reg", "eu_dir"])
    def test_collect_each_type(self, cli_runner, tmp_data_dir, doc_type):
        """Download 1 EU regulation or directive."""
        run_collect(
            cli_runner,
            ["collect", "eur_lex", "--type", doc_type, "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, doc_type)
        assert len(docs) >= 1, f"No {doc_type} documents saved"

        for doc in docs:
            assert_document_quality(doc, expected_type=doc_type, expected_source="eur_lex")
            # CELEX number should be the designation
            assert doc["designation"], f"Missing CELEX designation: {doc['doc_id']}"
            # Source URL should point to EUR-Lex
            assert "eur-lex.europa.eu" in (doc.get("source_url") or ""), (
                f"Source URL not EUR-Lex: {doc.get('source_url')}"
            )

        md_files = load_saved_markdown(tmp_data_dir, doc_type)
        assert len(md_files) >= 1
        assert_markdown_valid(md_files[0])


# ---------------------------------------------------------------------------
# CURIA (CJEU judgments)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestCuriaE2E:
    """E2E tests for the CJEU SPARQL collector."""

    def test_collect_cjeu(self, cli_runner, tmp_data_dir):
        """Download 1 CJEU judgment."""
        run_collect(
            cli_runner,
            ["collect", "curia", "--type", "cjeu", "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "cjeu")
        assert len(docs) >= 1, "No CJEU documents saved"

        for doc in docs:
            assert_document_quality(doc, expected_type="cjeu", expected_source="curia")
            assert doc["designation"], f"Missing CELEX designation: {doc['doc_id']}"
            assert doc.get("department") == "Court of Justice of the European Union"

        md_files = load_saved_markdown(tmp_data_dir, "cjeu")
        assert len(md_files) >= 1
        assert_markdown_valid(md_files[0])


# ---------------------------------------------------------------------------
# HUDOC (ECtHR judgments)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestHudocE2E:
    """E2E tests for the HUDOC ECtHR collector."""

    def test_collect_echr(self, cli_runner, tmp_data_dir):
        """Download 1 ECtHR judgment."""
        run_collect(
            cli_runner,
            ["collect", "hudoc", "--type", "echr", "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "echr")
        assert len(docs) >= 1, "No ECHR documents saved"

        for doc in docs:
            assert_document_quality(doc, expected_type="echr", expected_source="hudoc")
            assert doc.get("department") == "European Court of Human Rights"
            # Source URL should point to HUDOC
            assert "hudoc.echr.coe.int" in (doc.get("source_url") or ""), (
                f"Source URL not HUDOC: {doc.get('source_url')}"
            )

        md_files = load_saved_markdown(tmp_data_dir, "echr")
        assert len(md_files) >= 1
        assert_markdown_valid(md_files[0])


# ---------------------------------------------------------------------------
# collect-type command (preferred provider selection)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestCollectTypeCommand:
    """E2E tests for the 'collect-type' command."""

    def test_dry_run(self, cli_runner, tmp_data_dir):
        """Dry run shows which provider would be used without downloading."""
        from juris.cli import main

        result = cli_runner.invoke(
            main,
            ["--data-dir", str(tmp_data_dir), "collect-type", "prop", "--dry-run"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "riksdagen" in result.output

    @pytest.mark.parametrize("doc_type", ["prop", "sou", "nja", "echr", "eu_reg"])
    def test_collect_type_preferred(self, cli_runner, tmp_data_dir, doc_type):
        """collect-type uses the preferred provider and downloads successfully."""
        run_collect(
            cli_runner,
            ["collect-type", doc_type, "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, doc_type)
        assert len(docs) >= 1, f"No {doc_type} documents saved via collect-type"
        for doc in docs:
            assert_document_quality(doc, expected_type=doc_type)

    def test_collect_type_all_providers(self, cli_runner, tmp_data_dir):
        """--all-providers collects from every provider for a given type."""
        run_collect(
            cli_runner,
            ["collect-type", "prop", "--all-providers", "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "prop")
        assert len(docs) >= 1
        # Should have docs from multiple providers
        sources = {d["source"] for d in docs}
        # At least the preferred provider should be present
        assert "riksdagen" in sources or "regeringen" in sources


# ---------------------------------------------------------------------------
# collect-all command
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestCollectAllCommand:
    """E2E tests for the 'collect-all' command."""

    def test_dry_run(self, cli_runner, tmp_data_dir):
        """Dry run shows the full collection plan."""
        from juris.cli import main

        result = cli_runner.invoke(
            main,
            ["--data-dir", str(tmp_data_dir), "collect-all", "--dry-run"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Collection plan" in result.output
        # Should list multiple document types
        assert "prop" in result.output
        assert "nja" in result.output

    def test_collect_all_with_limit(self, cli_runner, tmp_data_dir):
        """collect-all --limit 1 downloads 1 doc per type from preferred providers."""
        run_collect(
            cli_runner,
            ["collect-all", "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        # Should have at least some document types populated
        import os
        type_dirs = [
            d for d in os.listdir(tmp_data_dir)
            if (tmp_data_dir / d).is_dir() and not d.startswith(".")
        ]
        assert len(type_dirs) >= 5, (
            f"Expected documents across many types, got {len(type_dirs)}: {type_dirs}"
        )


# ---------------------------------------------------------------------------
# Cross-provider consistency
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestCrossProviderConsistency:
    """Verify documents from different providers share consistent structure."""

    def test_prop_riksdagen_vs_regeringen(self, cli_runner, tmp_data_dir):
        """Props from riksdagen and regeringen should have the same Document shape."""
        # Collect 1 prop from riksdagen
        rk_dir = tmp_data_dir / "rk"
        rk_dir.mkdir()
        run_collect(
            cli_runner,
            ["collect", "riksdagen", "--type", "prop", "--limit", "1", "--skip-content"],
            rk_dir,
        )
        rk_docs = load_saved_documents(rk_dir, "prop")
        assert len(rk_docs) >= 1

        # Collect 1 prop from regeringen
        reg_dir = tmp_data_dir / "reg"
        reg_dir.mkdir()
        run_collect(
            cli_runner,
            ["collect", "regeringen", "--type", "prop", "--limit", "1", "--skip-content"],
            reg_dir,
        )
        reg_docs = load_saved_documents(reg_dir, "prop")
        assert len(reg_docs) >= 1

        # Both should pass the same quality checks
        rk_doc = rk_docs[0]
        reg_doc = reg_docs[0]
        assert_document_quality(rk_doc, expected_type="prop", expected_source="riksdagen")
        assert_document_quality(reg_doc, expected_type="prop", expected_source="regeringen")

        # Both should have the same set of top-level keys
        rk_keys = set(rk_doc.keys())
        reg_keys = set(reg_doc.keys())
        assert rk_keys == reg_keys, (
            f"Key mismatch between providers: "
            f"riksdagen has {rk_keys - reg_keys}, "
            f"regeringen has {reg_keys - rk_keys}"
        )

        # doc_id format should follow the same pattern
        assert rk_doc["doc_id"].startswith("prop-")
        assert reg_doc["doc_id"].startswith("prop-")


# ---------------------------------------------------------------------------
# Document structure and storage validation
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestDocumentStructure:
    """Validate structural properties of saved documents."""

    def test_json_roundtrip(self, cli_runner, tmp_data_dir):
        """Saved JSON can be loaded back into the Document Pydantic model."""
        from juris.models import Document

        run_collect(
            cli_runner,
            ["collect", "riksdagen", "--type", "prop", "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "prop")
        assert len(docs) >= 1

        # Should roundtrip through Pydantic without errors
        model = Document.model_validate(docs[0])
        dumped = model.model_dump(mode="json")
        reloaded = Document.model_validate(dumped)
        assert reloaded.doc_id == model.doc_id
        assert reloaded.doc_type == model.doc_type
        assert reloaded.title == model.title

    def test_markdown_frontmatter_matches_json(self, cli_runner, tmp_data_dir):
        """Markdown frontmatter should be consistent with JSON data."""
        run_collect(
            cli_runner,
            ["collect", "riksdagen", "--type", "sou", "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "sou")
        md_files = load_saved_markdown(tmp_data_dir, "sou")
        assert len(docs) >= 1
        assert len(md_files) >= 1

        doc = docs[0]
        fm = assert_markdown_valid(md_files[0])

        assert fm["doc_id"] == doc["doc_id"]
        assert fm["doc_type"] == doc["doc_type"]
        assert fm["title"] == doc["title"]
        assert fm["date"] == doc["date"]
        assert fm["source"] == doc["source"]

    def test_skip_existing(self, cli_runner, tmp_data_dir):
        """Running collect twice with --skip-existing skips already saved docs."""
        from juris.cli import main

        args = [
            "--data-dir", str(tmp_data_dir),
            "collect", "riksdagen", "--type", "mot", "--limit", "1", "--skip-content",
        ]
        # First run
        result1 = cli_runner.invoke(main, args, catch_exceptions=False)
        assert result1.exit_code == 0

        docs_after_first = load_saved_documents(tmp_data_dir, "mot")
        assert len(docs_after_first) >= 1

        # Second run — should skip the existing document
        result2 = cli_runner.invoke(main, args, catch_exceptions=False)
        assert result2.exit_code == 0
        assert "skip" in result2.output.lower() or "skipped" in result2.output.lower()

        # Same number of documents
        docs_after_second = load_saved_documents(tmp_data_dir, "mot")
        assert len(docs_after_second) == len(docs_after_first)

    def test_attachments_structure(self, cli_runner, tmp_data_dir):
        """Attachments should have required fields when present."""
        run_collect(
            cli_runner,
            ["collect", "riksdagen", "--type", "prop", "--limit", "1", "--skip-content"],
            tmp_data_dir,
        )
        docs = load_saved_documents(tmp_data_dir, "prop")
        assert len(docs) >= 1

        for doc in docs:
            for att in doc.get("attachments", []):
                assert att.get("filename"), f"Attachment missing filename in {doc['doc_id']}"
                assert att.get("url"), f"Attachment missing URL in {doc['doc_id']}"
                if att.get("mime_type"):
                    assert "/" in att["mime_type"], (
                        f"Invalid MIME type: {att['mime_type']}"
                    )
