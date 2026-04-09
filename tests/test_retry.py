"""Unit tests for retry logic in BaseCollector."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from juris.collectors.base import BaseCollector
from juris.models import DocType, Document, Source


class DummyCollector(BaseCollector):
    """Minimal concrete collector for testing base class methods."""

    # Use a dedicated flag to prevent this test double from being registered
    # in the global collector registry (which would overwrite a real collector).
    _skip_registration = True

    source = Source.RIKSDAGEN
    supported_doc_types = [DocType.PROP]

    def __init__(self) -> None:
        super().__init__(rate_limit=0.0, max_retries=2, backoff_base=0.01, backoff_factor=2.0)

    async def collect(self, doc_type, **kwargs):  # type: ignore[override]
        yield  # pragma: no cover

    async def get_document(self, source_id: str) -> Document | None:
        return None  # pragma: no cover


@pytest.mark.asyncio
async def test_fetch_with_retry_success_on_first_try() -> None:
    """Should return response immediately on 200."""
    collector = DummyCollector()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(return_value=mock_response)
    collector._client = mock_client

    resp = await collector._fetch_with_retry("GET", "https://example.com")
    assert resp.status_code == 200
    assert mock_client.request.call_count == 1
    await collector.close()


@pytest.mark.asyncio
async def test_fetch_with_retry_retries_on_503() -> None:
    """Should retry on 503 then succeed."""
    collector = DummyCollector()

    error_response = MagicMock(spec=httpx.Response)
    error_response.status_code = 503
    error_response.headers = {}

    ok_response = MagicMock(spec=httpx.Response)
    ok_response.status_code = 200
    ok_response.raise_for_status = MagicMock()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(side_effect=[error_response, ok_response])
    collector._client = mock_client

    resp = await collector._fetch_with_retry("GET", "https://example.com")
    assert resp.status_code == 200
    assert mock_client.request.call_count == 2
    await collector.close()


@pytest.mark.asyncio
async def test_fetch_with_retry_retries_on_timeout() -> None:
    """Should retry on TimeoutException then succeed."""
    collector = DummyCollector()

    ok_response = MagicMock(spec=httpx.Response)
    ok_response.status_code = 200
    ok_response.raise_for_status = MagicMock()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(side_effect=[httpx.ReadTimeout("timeout"), ok_response])
    collector._client = mock_client

    resp = await collector._fetch_with_retry("GET", "https://example.com")
    assert resp.status_code == 200
    assert mock_client.request.call_count == 2
    await collector.close()


@pytest.mark.asyncio
async def test_fetch_with_retry_exhausts_retries() -> None:
    """Should raise after all retries exhausted."""
    collector = DummyCollector()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
    collector._client = mock_client

    with pytest.raises(httpx.ReadTimeout):
        await collector._fetch_with_retry("GET", "https://example.com")

    # max_retries=2 means 3 total attempts (initial + 2 retries)
    assert mock_client.request.call_count == 3
    await collector.close()


@pytest.mark.asyncio
async def test_fetch_with_retry_respects_retry_after_header() -> None:
    """Should use Retry-After header value on 429."""
    collector = DummyCollector()

    rate_limited = MagicMock(spec=httpx.Response)
    rate_limited.status_code = 429
    rate_limited.headers = {"Retry-After": "1"}

    ok_response = MagicMock(spec=httpx.Response)
    ok_response.status_code = 200
    ok_response.raise_for_status = MagicMock()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(side_effect=[rate_limited, ok_response])
    collector._client = mock_client

    resp = await collector._fetch_with_retry("GET", "https://example.com")
    assert resp.status_code == 200
    await collector.close()


@pytest.mark.asyncio
async def test_fetch_with_retry_non_retryable_error() -> None:
    """Should raise immediately on non-retryable 4xx errors."""
    collector = DummyCollector()

    not_found = MagicMock(spec=httpx.Response)
    not_found.status_code = 404
    not_found.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("Not Found", request=MagicMock(), response=not_found)
    )

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(return_value=not_found)
    collector._client = mock_client

    with pytest.raises(httpx.HTTPStatusError):
        await collector._fetch_with_retry("GET", "https://example.com")

    assert mock_client.request.call_count == 1
    await collector.close()


# ---------------------------------------------------------------------------
# RiksdagenCollector._fetch_json integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_riksdagen_fetch_json_retries_on_503() -> None:
    """RiksdagenCollector._fetch_json should retry via _fetch_with_retry."""
    from juris.collectors.riksdagen import RiksdagenCollector

    collector = RiksdagenCollector(rate_limit=0.0)
    collector._max_retries = 2
    collector._backoff_base = 0.01

    error_response = MagicMock(spec=httpx.Response)
    error_response.status_code = 503
    error_response.headers = {}

    ok_response = MagicMock(spec=httpx.Response)
    ok_response.status_code = 200
    ok_response.raise_for_status = MagicMock()
    ok_response.json = MagicMock(return_value={"dokumentlista": {}})

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(side_effect=[error_response, ok_response])
    collector._client = mock_client

    result = await collector._fetch_json("https://data.riksdagen.se/dokumentlista/?doktyp=prop")
    assert result == {"dokumentlista": {}}
    assert mock_client.request.call_count == 2
    await collector.close()


@pytest.mark.asyncio
async def test_riksdagen_fetch_json_returns_none_on_permanent_failure() -> None:
    """RiksdagenCollector._fetch_json returns None after retries exhausted."""
    from juris.collectors.riksdagen import RiksdagenCollector

    collector = RiksdagenCollector(rate_limit=0.0)
    collector._max_retries = 1
    collector._backoff_base = 0.01

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
    collector._client = mock_client

    result = await collector._fetch_json("https://data.riksdagen.se/dokumentlista/?doktyp=prop")
    assert result is None
    assert mock_client.request.call_count == 2  # initial + 1 retry
    await collector.close()


@pytest.mark.asyncio
async def test_riksdagen_collect_captures_traffar() -> None:
    """RiksdagenCollector.collect should capture @traffar as total_available."""
    from juris.collectors.riksdagen import RiksdagenCollector

    collector = RiksdagenCollector(rate_limit=0.0)
    collector._max_retries = 0
    collector._backoff_base = 0.01

    api_response = MagicMock(spec=httpx.Response)
    api_response.status_code = 200
    api_response.raise_for_status = MagicMock()
    api_response.json = MagicMock(
        return_value={
            "dokumentlista": {
                "@traffar": "15432",
                "dokument": [
                    {
                        "dok_id": "H203AU1",
                        "doktyp": "prop",
                        "beteckning": "1",
                        "rm": "2024/25",
                        "titel": "Test proposition",
                        "datum": "2025-01-15",
                    }
                ],
            }
        }
    )

    # Second call for document HTML — return empty
    html_response = MagicMock(spec=httpx.Response)
    html_response.status_code = 200
    html_response.raise_for_status = MagicMock()
    html_response.json = MagicMock(return_value={"dokumentstatus": {"dokument": {"html": None}}})

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(side_effect=[api_response, html_response])
    collector._client = mock_client

    docs = []
    async for doc in collector.collect(DocType.PROP, limit=1):
        docs.append(doc)

    assert collector.total_available == 15432
    assert len(docs) == 1
    await collector.close()


# ---------------------------------------------------------------------------
# Riksdagen: improved error logging tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_riksdagen_fetch_json_logs_http_status_code(caplog: pytest.LogCaptureFixture) -> None:
    """_fetch_json should log the HTTP status code on HTTPStatusError."""
    from juris.collectors.riksdagen import RiksdagenCollector

    collector = RiksdagenCollector(rate_limit=0.0)
    collector._max_retries = 0
    collector._backoff_base = 0.01

    not_found = MagicMock(spec=httpx.Response)
    not_found.status_code = 404
    not_found.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("Not Found", request=MagicMock(), response=not_found)
    )

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(return_value=not_found)
    collector._client = mock_client

    with caplog.at_level("WARNING"):
        result = await collector._fetch_json("https://data.riksdagen.se/dokumentlista/?p=501")

    assert result is None
    assert collector._last_fetch_error == "HTTP 404"
    assert "HTTP 404" in caplog.text
    await collector.close()


@pytest.mark.asyncio
async def test_riksdagen_fetch_json_logs_network_error_type(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_fetch_json should log the exception type name on network errors."""
    from juris.collectors.riksdagen import RiksdagenCollector

    collector = RiksdagenCollector(rate_limit=0.0)
    collector._max_retries = 0
    collector._backoff_base = 0.01

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    collector._client = mock_client

    with caplog.at_level("WARNING"):
        result = await collector._fetch_json("https://data.riksdagen.se/dokumentlista/?p=1")

    assert result is None
    assert collector._last_fetch_error == "ConnectError: connection refused"
    assert "ConnectError: connection refused" in caplog.text
    await collector.close()


# ---------------------------------------------------------------------------
# Riksdagen: pagination end verification tests
# ---------------------------------------------------------------------------


def _make_api_response(
    documents: list[dict[str, str]] | None = None,
    next_page: str | None = None,
) -> MagicMock:
    """Build a mock httpx.Response that returns a Riksdagen-style JSON body."""
    body: dict[str, Any] = {"dokumentlista": {"@traffar": "100"}}
    if documents is not None:
        body["dokumentlista"]["dokument"] = documents
    if next_page:
        body["dokumentlista"]["@nasta_sida"] = next_page
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=body)
    return resp


def _make_error_response(status: int = 404) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(f"HTTP {status}", request=MagicMock(), response=resp)
    )
    return resp


@pytest.mark.asyncio
async def test_verify_pagination_end_confirms_end(caplog: pytest.LogCaptureFixture) -> None:
    """Should log 'Confirmed end of results' when prev OK and next also fails."""
    from juris.collectors.riksdagen import RiksdagenCollector

    collector = RiksdagenCollector(rate_limit=0.0)
    collector._max_retries = 0
    collector._backoff_base = 0.01

    prev_resp = _make_api_response(documents=[{"dok_id": "X"}])
    next_resp = _make_error_response(404)

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(side_effect=[prev_resp, next_resp])
    collector._client = mock_client

    with caplog.at_level("INFO"):
        await collector._verify_pagination_end(
            "https://data.riksdagen.se/dokumentlista/?p=50&doktyp=prop",
            None,
            980,
        )

    assert "Confirmed end of results" in caplog.text
    assert "980 documents" in caplog.text
    await collector.close()


@pytest.mark.asyncio
async def test_verify_pagination_end_warns_possible_block(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Should warn about possible block when previous page also fails."""
    from juris.collectors.riksdagen import RiksdagenCollector

    collector = RiksdagenCollector(rate_limit=0.0)
    collector._max_retries = 0
    collector._backoff_base = 0.01

    prev_resp = _make_error_response(403)
    next_resp = _make_error_response(403)

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(side_effect=[prev_resp, next_resp])
    collector._client = mock_client

    with caplog.at_level("WARNING"):
        await collector._verify_pagination_end(
            "https://data.riksdagen.se/dokumentlista/?p=50&doktyp=prop",
            None,
            980,
        )

    assert "Possible rate limit or block" in caplog.text
    await collector.close()


@pytest.mark.asyncio
async def test_verify_pagination_end_warns_gap(caplog: pytest.LogCaptureFixture) -> None:
    """Should warn about unexpected gap when next page succeeds."""
    from juris.collectors.riksdagen import RiksdagenCollector

    collector = RiksdagenCollector(rate_limit=0.0)
    collector._max_retries = 0
    collector._backoff_base = 0.01

    prev_resp = _make_api_response(documents=[{"dok_id": "X"}])
    next_resp = _make_api_response(documents=[{"dok_id": "Y"}])

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.request = AsyncMock(side_effect=[prev_resp, next_resp])
    collector._client = mock_client

    with caplog.at_level("WARNING"):
        await collector._verify_pagination_end(
            "https://data.riksdagen.se/dokumentlista/?p=50&doktyp=prop",
            None,
            980,
        )

    assert "Unexpected gap" in caplog.text
    await collector.close()


@pytest.mark.asyncio
async def test_verify_pagination_end_skips_without_page_param(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Should return silently when the URL has no 'p' parameter."""
    from juris.collectors.riksdagen import RiksdagenCollector

    collector = RiksdagenCollector(rate_limit=0.0)

    with caplog.at_level("INFO"):
        await collector._verify_pagination_end(
            "https://data.riksdagen.se/dokumentlista/?doktyp=prop&sida=1",
            None,
            0,
        )

    # No verification messages should be logged
    assert "Verifying" not in caplog.text
    await collector.close()
