import requests
import pytest

from lib.api import DataWars2Client, GW2Client
from lib.models import HistoryEntry, OrderBook


class DummyResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class DummySession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def get(self, url, params=None, timeout=None):
        del url, params, timeout
        self.call_count += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_fetch_history_batch_returns_all_ids_and_handles_failures(monkeypatch):
    client = DataWars2Client()

    def fake_fetch_history(item_id: int, days: int = 7):
        del days
        if item_id == 2:
            raise requests.RequestException("boom")
        return [HistoryEntry(date="2024-01-01", buy_sold=item_id)]

    monkeypatch.setattr(client, "fetch_history", fake_fetch_history)

    results = client.fetch_history_batch([1, 2, 3], days=30, max_workers=4)

    assert set(results.keys()) == {1, 2, 3}
    assert results[2] == []
    assert results[1][0].buy_sold == 1
    assert results[3][0].buy_sold == 3


def test_fetch_order_books_batch_returns_only_successful_results(monkeypatch):
    client = GW2Client()

    def fake_fetch_order_book(item_id: int):
        if item_id == 2:
            return None
        return OrderBook(item_id=item_id, buys=[{"unit_price": 10, "quantity": 1}])

    monkeypatch.setattr(client, "fetch_order_book", fake_fetch_order_book)

    results = client.fetch_order_books_batch([1, 2, 3], max_workers=3)

    assert set(results.keys()) == {1, 3}
    assert results[1].item_id == 1
    assert results[3].item_id == 3


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_request_retries_on_retriable_status(monkeypatch, status_code):
    client = DataWars2Client(rate_limit_delay=0.0, max_retries=2, backoff_base=0.01)
    session = DummySession([DummyResponse(status_code), DummyResponse(200)])
    sleep_calls = []

    monkeypatch.setattr(client, "_get_session", lambda: session)
    monkeypatch.setattr("lib.api.time.sleep", lambda seconds: sleep_calls.append(seconds))

    response = client._request("https://example.com/history")

    assert response.status_code == 200
    assert session.call_count == 2
    assert sleep_calls == [0.01]


def test_request_does_not_retry_non_retriable_4xx(monkeypatch):
    client = DataWars2Client(rate_limit_delay=0.0, max_retries=3, backoff_base=0.01)
    session = DummySession([DummyResponse(404)])
    sleep_calls = []

    monkeypatch.setattr(client, "_get_session", lambda: session)
    monkeypatch.setattr("lib.api.time.sleep", lambda seconds: sleep_calls.append(seconds))

    with pytest.raises(requests.HTTPError):
        client._request("https://example.com/history")

    assert session.call_count == 1
    assert sleep_calls == []
