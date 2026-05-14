"""Unit tests for parser functions across collectors."""

from __future__ import annotations

from datetime import date

from juris.collectors.domstol import (
    _parse_ad_reference,
    _parse_hfd_reference,
    _parse_mod_reference,
    _parse_nja_reference,
)
from juris.collectors.regeringen import _parse_designation
from juris.models import DocType
from juris.utils import (
    build_doc_id,
    html_to_text,
    parse_duration,
    parse_swedish_date,
    sanitize_filename,
)

# ---------------------------------------------------------------------------
# _parse_nja_reference
# ---------------------------------------------------------------------------


class TestParseNjaReference:
    def test_standard_colon_format(self) -> None:
        assert _parse_nja_reference(["NJA 2025:19"]) == ("19", "2025")

    def test_page_reference_format(self) -> None:
        assert _parse_nja_reference(["NJA 2025 s. 283"]) == ("283", "2025")

    def test_prefers_colon_over_page(self) -> None:
        refs = ["NJA 2025 s. 283", "NJA 2025:19"]
        assert _parse_nja_reference(refs) == ("19", "2025")

    def test_no_match(self) -> None:
        assert _parse_nja_reference(["Mål T 1234-25"]) == ("", None)

    def test_empty_list(self) -> None:
        assert _parse_nja_reference([]) == ("", None)

    def test_multiple_refs_first_colon_wins(self) -> None:
        refs = ["NJA 2024:5", "NJA 2024:10"]
        assert _parse_nja_reference(refs) == ("5", "2024")

    def test_whitespace_handling(self) -> None:
        assert _parse_nja_reference(["  NJA 2023:42  "]) == ("42", "2023")


# ---------------------------------------------------------------------------
# _parse_ad_reference
# ---------------------------------------------------------------------------


class TestParseAdReference:
    def test_standard_format(self) -> None:
        assert _parse_ad_reference(["AD 2025 nr 19"]) == ("19", "2025")

    def test_no_match(self) -> None:
        assert _parse_ad_reference(["Something else"]) == ("", None)

    def test_empty_list(self) -> None:
        assert _parse_ad_reference([]) == ("", None)


# ---------------------------------------------------------------------------
# _parse_hfd_reference
# ---------------------------------------------------------------------------


class TestParseHfdReference:
    def test_hfd_format(self) -> None:
        assert _parse_hfd_reference(["HFD 2021 ref. 56"]) == ("56", "2021")

    def test_legacy_ra_format(self) -> None:
        assert _parse_hfd_reference(["RÅ 2010 ref. 19"]) == ("19", "2010")

    def test_no_match(self) -> None:
        assert _parse_hfd_reference(["Not a reference"]) == ("", None)


# ---------------------------------------------------------------------------
# _parse_mod_reference
# ---------------------------------------------------------------------------


class TestParseModReference:
    def test_standard_format(self) -> None:
        assert _parse_mod_reference(["MÖD 2011:26"]) == ("26", "2011")

    def test_no_match(self) -> None:
        assert _parse_mod_reference(["Not MÖD"]) == ("", None)


# ---------------------------------------------------------------------------
# _parse_designation (Regeringen.se)
# ---------------------------------------------------------------------------


class TestParseDesignation:
    def test_prop(self) -> None:
        assert _parse_designation("Prop. 2025/26:229", DocType.PROP) == ("229", "2025/26")

    def test_sou(self) -> None:
        assert _parse_designation("SOU 2024:42", DocType.SOU) == ("42", "2024")

    def test_ds(self) -> None:
        assert _parse_designation("Ds 2026:6", DocType.DS) == ("6", "2026")

    def test_ds_alternate_format(self) -> None:
        assert _parse_designation("ds-2026-6", DocType.DS) == ("6", "2026")

    def test_dir(self) -> None:
        assert _parse_designation("Dir. 2024:100", DocType.DIR) == ("100", "2024")

    def test_skr(self) -> None:
        assert _parse_designation("Skr. 2024/25:10", DocType.SKR) == ("10", "2024/25")

    def test_lagr_pattern(self) -> None:
        # lagr has a pattern for "Lagrådsremiss YYYY:N"
        assert _parse_designation("Lagrådsremiss 2025:3", DocType.LAGR) == ("3", "2025")

    def test_ds_concatenated_url(self) -> None:
        assert _parse_designation("ds-20262", DocType.DS) == ("2", "2026")

    def test_ds_concatenated_no_separator(self) -> None:
        assert _parse_designation("ds20262", DocType.DS) == ("2", "2026")

    def test_ds_concatenated_double_digit(self) -> None:
        assert _parse_designation("ds202612", DocType.DS) == ("12", "2026")

    def test_ds_concatenated_url_with_slash(self) -> None:
        assert _parse_designation("/ds-20268/", DocType.DS) == ("8", "2026")

    def test_no_match(self) -> None:
        assert _parse_designation("No designation here", DocType.PROP) == ("", None)

    def test_in_longer_text(self) -> None:
        text = "Regeringens proposition Prop. 2023/24:100 om något viktigt"
        assert _parse_designation(text, DocType.PROP) == ("100", "2023/24")


# ---------------------------------------------------------------------------
# build_doc_id
# ---------------------------------------------------------------------------


class TestBuildDocId:
    def test_with_session(self) -> None:
        assert build_doc_id(DocType.PROP, "208", "2024/25") == "prop-2024/25:208"

    def test_without_session(self) -> None:
        assert build_doc_id(DocType.SOU, "42") == "sou-42"

    def test_sfs(self) -> None:
        assert build_doc_id(DocType.SFS, "123", "2024") == "sfs-2024:123"


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    def test_prop(self) -> None:
        assert sanitize_filename("prop-2024/25:208") == "prop-2024-25_208"

    def test_foreskrift_with_spaces(self) -> None:
        assert sanitize_filename("foreskrift-2023:AFS 2023:1") == "foreskrift-2023_AFS-2023_1"

    def test_simple_id(self) -> None:
        assert sanitize_filename("sou-42") == "sou-42"


# ---------------------------------------------------------------------------
# parse_swedish_date
# ---------------------------------------------------------------------------


class TestParseSwedishDate:
    def test_standard_format(self) -> None:
        assert parse_swedish_date("02 april 2026") == date(2026, 4, 2)

    def test_single_digit_day(self) -> None:
        assert parse_swedish_date("1 januari 2025") == date(2025, 1, 1)

    def test_december(self) -> None:
        assert parse_swedish_date("31 december 2024") == date(2024, 12, 31)

    def test_invalid_month(self) -> None:
        assert parse_swedish_date("15 foobar 2024") is None

    def test_no_match(self) -> None:
        assert parse_swedish_date("not a date") is None

    def test_in_longer_text(self) -> None:
        assert parse_swedish_date("Publicerad 15 mars 2025 kl 10:00") == date(2025, 3, 15)


# ---------------------------------------------------------------------------
# html_to_text
# ---------------------------------------------------------------------------


class TestHtmlToText:
    def test_basic(self) -> None:
        html = "<p>Hello</p><p>World</p>"
        result = html_to_text(html)
        assert "Hello" in result
        assert "World" in result

    def test_strips_scripts(self) -> None:
        html = "<p>Text</p><script>alert('x')</script>"
        result = html_to_text(html)
        assert "alert" not in result
        assert "Text" in result

    def test_strips_styles(self) -> None:
        html = "<style>.x{color:red}</style><p>Content</p>"
        result = html_to_text(html)
        assert "color" not in result
        assert "Content" in result


class TestParseDuration:
    def test_zero(self) -> None:
        assert parse_duration("0") == 0

    def test_seconds(self) -> None:
        assert parse_duration("90s") == 90
        assert parse_duration("90") == 90

    def test_minutes(self) -> None:
        assert parse_duration("30m") == 1800

    def test_hours(self) -> None:
        assert parse_duration("6h") == 6 * 3600

    def test_days(self) -> None:
        assert parse_duration("2d") == 2 * 86400

    def test_uppercase_unit(self) -> None:
        assert parse_duration("6H") == 6 * 3600

    def test_whitespace(self) -> None:
        assert parse_duration("  6h ") == 6 * 3600

    def test_invalid(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            parse_duration("6 hours")
        with pytest.raises(ValueError):
            parse_duration("abc")
