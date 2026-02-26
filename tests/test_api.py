import pytest

from lib.api import DataWars2Client, GW2Client
from lib.models import HistoryEntry, OrderBook


class DummyResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.text = text
        self.request = None

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=self.request, response=self)


class DummyAsyncClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    async def get(self, url, params=None, timeout=None):
        del url, params, timeout
        self.call_count += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_fetch_history_batch_returns_all_ids_and_handles_failures(monkeypatch):
    client = DataWars2Client()

    async def fake_fetch_history(item_id: int, days: int = 7):
        del days
        if item_id == 2:
            raise Exception("boom")
        return [HistoryEntry(date="2024-01-01", buy_sold=item_id)]

    monkeypatch.setattr(client, "fetch_history", fake_fetch_history)

    results = await client.fetch_history_batch([1, 2, 3], days=30, max_concurrent=4)

    assert set(results.keys()) == {1, 2, 3}
    assert results[2] == []
    assert results[1][0].buy_sold == 1
    assert results[3][0].buy_sold == 3


@pytest.mark.asyncio
async def test_fetch_order_books_batch_returns_only_successful_results(monkeypatch):
    client = GW2Client()

    async def fake_fetch_order_books_chunk(item_ids: list[int]):
        results = {}
        for item_id in item_ids:
            if item_id == 2:
                continue
            results[item_id] = OrderBook(
                item_id=item_id,
                buys=[{"unit_price": 10, "quantity": 1}],
            )
        return results

    monkeypatch.setattr(client, "_fetch_order_books_chunk", fake_fetch_order_books_chunk)

    results = await client.fetch_order_books_batch([1, 2, 3], max_concurrent=3)

    assert set(results.keys()) == {1, 3}
    assert results[1].item_id == 1
    assert results[3].item_id == 3


@pytest.mark.asyncio
async def test_request_retries_on_retriable_status(monkeypatch):
    import httpx

    client = DataWars2Client(rate_limit_delay=0.0, max_retries=2, backoff_base=0.01)
    responses = [DummyResponse(429), DummyResponse(200)]
    client._client = DummyAsyncClient(responses)
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr("lib.api.asyncio.sleep", fake_sleep)

    response = await client._request("https://example.com/history")

    assert response.status_code == 200
    assert client._client.call_count == 2
    assert sleep_calls == [0.01]


@pytest.mark.asyncio
async def test_request_does_not_retry_non_retriable_4xx(monkeypatch):
    import httpx

    client = DataWars2Client(rate_limit_delay=0.0, max_retries=3, backoff_base=0.01)
    responses = [DummyResponse(404)]
    client._client = DummyAsyncClient(responses)
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr("lib.api.asyncio.sleep", fake_sleep)

    with pytest.raises(httpx.HTTPStatusError):
        await client._request("https://example.com/history")

    assert client._client.call_count == 1
    assert sleep_calls == []
