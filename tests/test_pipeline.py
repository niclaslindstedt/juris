"""Unit tests for the collection pipeline."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from juris.collectors.base import BaseCollector
from juris.models import DocType, Document, Source
from juris.pipeline import collect_from_source
from juris.state import CollectionState, load_state, save_state


class _FakeCollector(BaseCollector):
    """Minimal collector for testing pipeline logic."""

    _skip_registration = True
    source = Source.REGERINGEN
    supported_doc_types = [DocType.DS]

    def __init__(self) -> None:
        super().__init__(rate_limit=0)
        self.received_since: date | None = None

    async def collect(
        self,
        doc_type: DocType,
        *,
        session: str | None = None,
        since: date | None = None,
        until: date | None = None,
        limit: int | None = None,
        skip_content: bool = False,
    ) -> AsyncIterator[Document]:
        self.received_since = since
        doc = Document(
            doc_id="ds-2026:99",
            doc_type=DocType.DS,
            designation="99",
            session="2026",
            title="Test DS document",
            date=date(2026, 4, 1),
            source=Source.REGERINGEN,
            source_id="/test",
            source_url="https://example.com/test",
            fetched_at=datetime.now(tz=UTC),
        )
        yield doc

    async def get_document(self, source_id: str) -> Document | None:
        return None


@pytest.fixture()
def _patch_collector(monkeypatch: pytest.MonkeyPatch) -> _FakeCollector:
    """Patch get_collector_class to return our fake collector."""
    fake = _FakeCollector()

    def _fake_get_class(source_name: str) -> type[BaseCollector]:
        # Return a class whose __init__ returns our pre-built fake
        class _Wrapper(_FakeCollector):
            _skip_registration = True

            def __new__(cls) -> _Wrapper:  # type: ignore[misc]
                return fake  # type: ignore[return-value]

        return _Wrapper

    monkeypatch.setattr("juris.pipeline.get_collector_class", _fake_get_class)
    return fake


class TestAutoIncremental:
    """Tests for auto-setting since from state."""

    @pytest.mark.usefixtures("_patch_collector")
    async def test_auto_since_from_state(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        """When state has last_fetched_date and since is None, auto-set since."""
        state = CollectionState(
            source=Source.REGERINGEN,
            doc_type=DocType.DS,
            last_fetched_date="2026-03-15",
            total_collected=10,
        )
        save_state(state, tmp_data_dir)

        await collect_from_source("regeringen", DocType.DS, tmp_data_dir)

        assert _patch_collector.received_since == date(2026, 3, 13)

    @pytest.mark.usefixtures("_patch_collector")
    async def test_explicit_since_overrides_state(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        """When user provides explicit since, it takes precedence over state."""
        state = CollectionState(
            source=Source.REGERINGEN,
            doc_type=DocType.DS,
            last_fetched_date="2026-03-15",
            total_collected=10,
        )
        save_state(state, tmp_data_dir)

        explicit_since = date(2026, 1, 1)
        await collect_from_source("regeringen", DocType.DS, tmp_data_dir, since=explicit_since)

        assert _patch_collector.received_since == explicit_since

    @pytest.mark.usefixtures("_patch_collector")
    async def test_no_auto_since_without_state(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        """When state has no last_fetched_date, since stays None."""
        await collect_from_source("regeringen", DocType.DS, tmp_data_dir)

        assert _patch_collector.received_since is None

    @pytest.mark.usefixtures("_patch_collector")
    async def test_no_auto_since_when_skip_existing_false(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        """When skip_existing is False, since stays None even with state."""
        state = CollectionState(
            source=Source.REGERINGEN,
            doc_type=DocType.DS,
            last_fetched_date="2026-03-15",
            total_collected=10,
        )
        save_state(state, tmp_data_dir)

        await collect_from_source("regeringen", DocType.DS, tmp_data_dir, skip_existing=False)

        assert _patch_collector.received_since is None


class TestTotalAvailablePropagation:
    """Tests for total_available propagation from collector to state."""

    @pytest.mark.usefixtures("_patch_collector")
    async def test_total_available_saved_to_state(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        """When collector sets total_available, it should be saved to state."""
        _patch_collector.total_available = 500

        await collect_from_source("regeringen", DocType.DS, tmp_data_dir, skip_existing=False)

        state = load_state(tmp_data_dir, Source.REGERINGEN, DocType.DS)
        assert state.total_available == 500

    @pytest.mark.usefixtures("_patch_collector")
    async def test_total_available_none_preserves_existing(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        """When collector has no total_available, existing state value is kept."""
        existing = CollectionState(
            source=Source.REGERINGEN,
            doc_type=DocType.DS,
            total_available=300,
        )
        save_state(existing, tmp_data_dir)

        # _patch_collector.total_available is None by default
        await collect_from_source("regeringen", DocType.DS, tmp_data_dir, skip_existing=False)

        state = load_state(tmp_data_dir, Source.REGERINGEN, DocType.DS)
        assert state.total_available == 300
