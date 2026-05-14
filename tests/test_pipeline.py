"""Unit tests for the collection pipeline."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from juris.collectors.base import BaseCollector
from juris.index import load_index
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


class TestIndexSideEffect:
    """The remote index should be populated as a side effect of collection."""

    @pytest.mark.usefixtures("_patch_collector")
    async def test_full_run_marks_index_complete(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        _patch_collector.total_available = 1

        await collect_from_source("regeringen", DocType.DS, tmp_data_dir, skip_existing=False)

        idx = load_index(tmp_data_dir, Source.REGERINGEN, DocType.DS)
        assert idx is not None
        assert idx.complete is True
        assert idx.total_available == 1
        assert [e.doc_id for e in idx.entries] == ["ds-2026:99"]
        assert len(idx.pages) == 1
        assert idx.pages[0].doc_ids == ["ds-2026:99"]

    @pytest.mark.usefixtures("_patch_collector")
    async def test_filtered_run_leaves_index_incomplete(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        await collect_from_source(
            "regeringen", DocType.DS, tmp_data_dir, limit=1, skip_existing=False
        )

        idx = load_index(tmp_data_dir, Source.REGERINGEN, DocType.DS)
        assert idx is not None
        assert idx.complete is False
        assert [e.doc_id for e in idx.entries] == ["ds-2026:99"]

    @pytest.mark.usefixtures("_patch_collector")
    async def test_no_update_index_skips_write(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        await collect_from_source(
            "regeringen",
            DocType.DS,
            tmp_data_dir,
            skip_existing=False,
            update_index=False,
        )

        assert load_index(tmp_data_dir, Source.REGERINGEN, DocType.DS) is None

    @pytest.mark.usefixtures("_patch_collector")
    async def test_on_total_fired_when_known(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        _patch_collector.total_available = 42
        seen: list[int] = []

        class _Capture:
            def on_save(self, doc_id: str, path: Path) -> None: ...
            def on_skip(self, doc_id: str) -> None: ...
            def on_total(self, total: int) -> None:
                seen.append(total)

            def on_finish(self) -> None: ...

        await collect_from_source(
            "regeringen",
            DocType.DS,
            tmp_data_dir,
            skip_existing=False,
            progress=_Capture(),
        )

        assert seen == [42]


class TestMaxAge:
    """Freshness short-circuit via ``max_age_seconds``."""

    @pytest.mark.usefixtures("_patch_collector")
    async def test_full_run_records_last_full_run_at(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        await collect_from_source("regeringen", DocType.DS, tmp_data_dir, skip_existing=False)

        state = load_state(tmp_data_dir, Source.REGERINGEN, DocType.DS)
        assert state.last_full_run_at is not None

    @pytest.mark.usefixtures("_patch_collector")
    async def test_filtered_run_does_not_record_last_full_run_at(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        await collect_from_source(
            "regeringen", DocType.DS, tmp_data_dir, limit=1, skip_existing=False
        )

        state = load_state(tmp_data_dir, Source.REGERINGEN, DocType.DS)
        assert state.last_full_run_at is None

    @pytest.mark.usefixtures("_patch_collector")
    async def test_skips_when_fresh(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        # Pretend a full run just completed.
        state = CollectionState(
            source=Source.REGERINGEN,
            doc_type=DocType.DS,
            last_full_run_at=datetime.now(tz=UTC).isoformat(),
        )
        save_state(state, tmp_data_dir)

        collected, skipped = await collect_from_source(
            "regeringen", DocType.DS, tmp_data_dir, max_age_seconds=3600
        )

        assert (collected, skipped) == (0, 0)
        # Collector's collect() should not have been invoked.
        assert _patch_collector.received_since is None

    @pytest.mark.usefixtures("_patch_collector")
    async def test_runs_when_stale(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        old = datetime.now(tz=UTC) - timedelta(hours=24)
        state = CollectionState(
            source=Source.REGERINGEN,
            doc_type=DocType.DS,
            last_full_run_at=old.isoformat(),
        )
        save_state(state, tmp_data_dir)

        collected, skipped = await collect_from_source(
            "regeringen", DocType.DS, tmp_data_dir, max_age_seconds=3600, skip_existing=False
        )

        assert collected == 1

    @pytest.mark.usefixtures("_patch_collector")
    async def test_ignored_with_filters(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        """Filtered invocations bypass the freshness short-circuit."""
        state = CollectionState(
            source=Source.REGERINGEN,
            doc_type=DocType.DS,
            last_full_run_at=datetime.now(tz=UTC).isoformat(),
        )
        save_state(state, tmp_data_dir)

        collected, skipped = await collect_from_source(
            "regeringen",
            DocType.DS,
            tmp_data_dir,
            limit=1,
            max_age_seconds=3600,
            skip_existing=False,
        )

        assert collected == 1

    @pytest.mark.usefixtures("_patch_collector")
    async def test_on_fresh_callback_fires(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        state = CollectionState(
            source=Source.REGERINGEN,
            doc_type=DocType.DS,
            last_full_run_at=datetime.now(tz=UTC).isoformat(),
        )
        save_state(state, tmp_data_dir)

        seen: list[tuple[float, int]] = []

        class _Capture:
            def on_save(self, doc_id: str, path: Path) -> None: ...
            def on_skip(self, doc_id: str) -> None: ...
            def on_fresh(self, age_seconds: float, max_age_seconds: int) -> None:
                seen.append((age_seconds, max_age_seconds))

            def on_finish(self) -> None: ...

        await collect_from_source(
            "regeringen", DocType.DS, tmp_data_dir, max_age_seconds=3600, progress=_Capture()
        )

        assert len(seen) == 1
        assert seen[0][1] == 3600


class TestDedup:
    @pytest.mark.usefixtures("_patch_collector")
    async def test_dedup_against_existing_entries(
        self, tmp_data_dir: Path, _patch_collector: _FakeCollector
    ) -> None:
        # First run: writes one entry.
        await collect_from_source("regeringen", DocType.DS, tmp_data_dir, skip_existing=False)
        # Second run yields the same doc — index must not duplicate it.
        await collect_from_source("regeringen", DocType.DS, tmp_data_dir, skip_existing=False)

        idx = load_index(tmp_data_dir, Source.REGERINGEN, DocType.DS)
        assert idx is not None
        assert [e.doc_id for e in idx.entries] == ["ds-2026:99"]
