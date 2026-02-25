import csv
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional

import requests

from lib.models import HistoryEntry, ItemPrice, OrderBook

RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class DataWars2Client:
    BASE_URL = "https://api.datawars2.ie/gw2/v1"

    def __init__(
        self,
        timeout: int = 30,
        rate_limit_delay: float = 0.0,
        max_retries: int = 3,
        backoff_base: float = 0.25,
    ):
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._thread_local = threading.local()

    def _get_session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            self._thread_local.session = session
        return session

    def _request(self, url: str, params: Optional[dict] = None) -> requests.Response:
        for attempt in range(self.max_retries + 1):
            session = self._get_session()
            try:
                response = session.get(url, params=params, timeout=self.timeout)
                if response.status_code in RETRIABLE_STATUS_CODES:
                    raise requests.HTTPError(
                        f"Retriable HTTP status: {response.status_code}",
                        response=response,
                    )
                response.raise_for_status()
                if self.rate_limit_delay > 0:
                    time.sleep(self.rate_limit_delay)
                return response
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response else None
                should_retry = status_code in RETRIABLE_STATUS_CODES
                if not should_retry or attempt >= self.max_retries:
                    raise
            except requests.RequestException:
                if attempt >= self.max_retries:
                    raise

            backoff_seconds = self.backoff_base * (2**attempt)
            if backoff_seconds > 0:
                time.sleep(backoff_seconds)

        raise RuntimeError("Unreachable: request loop exited without returning/raising")

    def fetch_all_items(self) -> list[ItemPrice]:
        url = f"{self.BASE_URL}/items/csv"
        response = self._request(url)

        items = []
        reader = csv.DictReader(io.StringIO(response.text))
        for row in reader:
            try:
                item = ItemPrice(
                    id=int(row["id"]),
                    name=row.get("name", ""),
                    buy_price=self._parse_int(row.get("buy_price")),
                    sell_price=self._parse_int(row.get("sell_price")),
                    buy_quantity=self._parse_int(row.get("buy_quantity")),
                    sell_quantity=self._parse_int(row.get("sell_quantity")),
                )
                items.append(item)
            except (ValueError, KeyError):
                continue

        return items

    def fetch_history(self, item_id: int, days: int = 7) -> list[HistoryEntry]:
        url = f"{self.BASE_URL}/history"
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        params = {
            "itemID": item_id,
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        }

        response = self._request(url, params)
        data = response.json()

        entries = []
        for item in data:
            entry = HistoryEntry(
                date=item.get("date", ""),
                buy_sold=item.get("buy_sold", 0),
                sell_sold=item.get("sell_sold", 0),
                buy_value=item.get("buy_value", 0),
                sell_value=item.get("sell_value", 0),
                buy_listed=item.get("buy_listed", 0),
                sell_listed=item.get("sell_listed", 0),
                buy_delisted=item.get("buy_delisted", 0),
                sell_delisted=item.get("sell_delisted", 0),
                buy_price_avg=item.get("buy_price_avg"),
                buy_price_min=item.get("buy_price_min"),
                buy_price_max=item.get("buy_price_max"),
                buy_price_stdev=item.get("buy_price_stdev"),
                sell_price_avg=item.get("sell_price_avg"),
                sell_price_min=item.get("sell_price_min"),
                sell_price_max=item.get("sell_price_max"),
                sell_price_stdev=item.get("sell_price_stdev"),
                buy_quantity_avg=item.get("buy_quantity_avg"),
                sell_quantity_avg=item.get("sell_quantity_avg"),
                count=item.get("count", 0),
            )
            entries.append(entry)

        return entries

    def fetch_history_batch(
        self,
        item_ids: list[int],
        days: int = 1,
        max_workers: int = 32,
    ) -> dict[int, list[HistoryEntry]]:
        if not item_ids:
            return {}

        worker_count = max(1, min(max_workers, len(item_ids)))
        results = {item_id: [] for item_id in item_ids}

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_item_id = {
                executor.submit(self.fetch_history, item_id, days): item_id
                for item_id in item_ids
            }
            for future in as_completed(future_to_item_id):
                item_id = future_to_item_id[future]
                try:
                    results[item_id] = future.result()
                except requests.RequestException:
                    results[item_id] = []
        return results

    @staticmethod
    def _parse_int(value: Optional[str]) -> Optional[int]:
        if value is None or value == "" or value == "None":
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None


class GW2Client:
    BASE_URL = "https://api.guildwars2.com/v2"

    def __init__(
        self,
        timeout: int = 30,
        rate_limit_delay: float = 0.0,
        max_retries: int = 3,
        backoff_base: float = 0.25,
    ):
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._thread_local = threading.local()

    def _get_session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            self._thread_local.session = session
        return session

    def _request(self, url: str) -> requests.Response:
        for attempt in range(self.max_retries + 1):
            session = self._get_session()
            try:
                response = session.get(url, timeout=self.timeout)
                if response.status_code in RETRIABLE_STATUS_CODES:
                    raise requests.HTTPError(
                        f"Retriable HTTP status: {response.status_code}",
                        response=response,
                    )
                response.raise_for_status()
                if self.rate_limit_delay > 0:
                    time.sleep(self.rate_limit_delay)
                return response
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response else None
                should_retry = status_code in RETRIABLE_STATUS_CODES
                if not should_retry or attempt >= self.max_retries:
                    raise
            except requests.RequestException:
                if attempt >= self.max_retries:
                    raise

            backoff_seconds = self.backoff_base * (2**attempt)
            if backoff_seconds > 0:
                time.sleep(backoff_seconds)

        raise RuntimeError("Unreachable: request loop exited without returning/raising")

    def fetch_order_book(self, item_id: int) -> Optional[OrderBook]:
        url = f"{self.BASE_URL}/commerce/listings/{item_id}"
        try:
            response = self._request(url)
            data = response.json()
            return OrderBook(
                item_id=item_id,
                buys=data.get("buys", []),
                sells=data.get("sells", []),
            )
        except requests.RequestException:
            return None

    def fetch_items_batch(self, item_ids: list[int]) -> dict[int, dict]:
        """Fetch item details (like vendor_value) from GW2 API in batches of 200."""
        results = {}
        # API allows max 200 ids per request
        chunk_size = 200
        for i in range(0, len(item_ids), chunk_size):
            chunk = item_ids[i:i + chunk_size]
            ids_str = ",".join(map(str, chunk))
            url = f"{self.BASE_URL}/items?ids={ids_str}"
            try:
                response = self._request(url)
                data = response.json()
                for item in data:
                    results[item["id"]] = item
            except requests.RequestException:
                continue
        return results

    def fetch_order_books_batch(
        self, item_ids: list[int], max_workers: int = 32
    ) -> dict[int, OrderBook]:
        if not item_ids:
            return {}

        worker_count = max(1, min(max_workers, len(item_ids)))
        results: dict[int, OrderBook] = {}

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_item_id = {
                executor.submit(self.fetch_order_book, item_id): item_id
                for item_id in item_ids
            }
            for future in as_completed(future_to_item_id):
                item_id = future_to_item_id[future]
                order_book = future.result()
                if order_book:
                    results[item_id] = order_book
        return results
