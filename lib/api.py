import asyncio
import csv
import io
from datetime import datetime, timedelta
from typing import Optional

import httpx

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
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, url: str, params: Optional[dict] = None) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            client = await self._get_client()
            try:
                response = await client.get(url, params=params)
                if response.status_code in RETRIABLE_STATUS_CODES:
                    raise httpx.HTTPStatusError(
                        f"Retriable HTTP status: {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                if self.rate_limit_delay > 0:
                    await asyncio.sleep(self.rate_limit_delay)
                return response
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response else None
                should_retry = status_code in RETRIABLE_STATUS_CODES
                if not should_retry or attempt >= self.max_retries:
                    raise
            except httpx.RequestError:
                if attempt >= self.max_retries:
                    raise

            backoff_seconds = self.backoff_base * (2**attempt)
            if backoff_seconds > 0:
                await asyncio.sleep(backoff_seconds)

        raise RuntimeError("Unreachable: request loop exited without returning/raising")

    async def fetch_all_items(self) -> list[ItemPrice]:
        url = f"{self.BASE_URL}/items/csv"
        response = await self._request(url)

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

    async def fetch_history(self, item_id: int, days: int = 7) -> list[HistoryEntry]:
        url = f"{self.BASE_URL}/history"
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        params = {
            "itemID": item_id,
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        }

        response = await self._request(url, params)
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

    async def fetch_history_batch(
        self,
        item_ids: list[int],
        days: int = 1,
        max_concurrent: int = 32,
    ) -> dict[int, list[HistoryEntry]]:
        if not item_ids:
            return {}

        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_semaphore(item_id: int) -> tuple[int, list[HistoryEntry]]:
            async with semaphore:
                try:
                    result = await self.fetch_history(item_id, days)
                    return (item_id, result)
                except Exception:
                    return (item_id, [])

        tasks = [fetch_with_semaphore(item_id) for item_id in item_ids]
        results_list = await asyncio.gather(*tasks)
        return dict(results_list)

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
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, url: str) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            client = await self._get_client()
            try:
                response = await client.get(url)
                if response.status_code in RETRIABLE_STATUS_CODES:
                    raise httpx.HTTPStatusError(
                        f"Retriable HTTP status: {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                if self.rate_limit_delay > 0:
                    await asyncio.sleep(self.rate_limit_delay)
                return response
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response else None
                should_retry = status_code in RETRIABLE_STATUS_CODES
                if not should_retry or attempt >= self.max_retries:
                    raise
            except httpx.RequestError:
                if attempt >= self.max_retries:
                    raise

            backoff_seconds = self.backoff_base * (2**attempt)
            if backoff_seconds > 0:
                await asyncio.sleep(backoff_seconds)

        raise RuntimeError("Unreachable: request loop exited without returning/raising")

    async def fetch_order_book(self, item_id: int) -> Optional[OrderBook]:
        url = f"{self.BASE_URL}/commerce/listings/{item_id}"
        try:
            response = await self._request(url)
            data = response.json()
            return OrderBook(
                item_id=item_id,
                buys=data.get("buys", []),
                sells=data.get("sells", []),
            )
        except httpx.HTTPStatusError:
            return None
        except httpx.RequestError:
            return None

    async def fetch_items_batch(self, item_ids: list[int]) -> dict[int, dict]:
        results = {}
        chunk_size = 200
        for i in range(0, len(item_ids), chunk_size):
            chunk = item_ids[i:i + chunk_size]
            ids_str = ",".join(map(str, chunk))
            url = f"{self.BASE_URL}/items?ids={ids_str}"
            try:
                response = await self._request(url)
                data = response.json()
                for item in data:
                    results[item["id"]] = item
            except httpx.HTTPStatusError:
                continue
            except httpx.RequestError:
                continue
        return results

    async def fetch_order_books_batch(
        self, item_ids: list[int], max_concurrent: int = 32
    ) -> dict[int, OrderBook]:
        if not item_ids:
            return {}

        chunk_size = 200
        item_chunks = [
            item_ids[i:i + chunk_size]
            for i in range(0, len(item_ids), chunk_size)
        ]

        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_chunk(chunk: list[int]) -> dict[int, OrderBook]:
            async with semaphore:
                return await self._fetch_order_books_chunk(chunk)

        tasks = [fetch_chunk(chunk) for chunk in item_chunks]
        results_list = await asyncio.gather(*tasks)

        results: dict[int, OrderBook] = {}
        for chunk_results in results_list:
            results.update(chunk_results)

        return results

    async def _fetch_order_books_chunk(self, item_ids: list[int]) -> dict[int, OrderBook]:
        if not item_ids:
            return {}

        ids_str = ",".join(map(str, item_ids))
        url = f"{self.BASE_URL}/commerce/listings?ids={ids_str}"

        try:
            response = await self._request(url)
            data = response.json()
            results = {}
            for item_data in data:
                item_id = item_data.get("id")
                if item_id is not None:
                    results[item_id] = OrderBook(
                        item_id=item_id,
                        buys=item_data.get("buys", []),
                        sells=item_data.get("sells", []),
                    )
            return results
        except httpx.HTTPStatusError:
            return {}
        except httpx.RequestError:
            return {}
