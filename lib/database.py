import sqlite3
from datetime import datetime
from typing import Optional

from lib.calculator import calc_flip_score, calc_percent_profit
from lib.models import Item, ItemPrice

HistoryUpdateRow = tuple[
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    float,
    float,
    float,
    Optional[int],
    Optional[int],
]
OrderBookUpdateRow = tuple[int, float, int]


class Database:
    def __init__(self, db_path: str = "gw2.db"):
        self.db_path = db_path
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                buy_price INTEGER,
                sell_price INTEGER,
                buy_quantity INTEGER,
                sell_quantity INTEGER,
                vendor_value INTEGER,
                buy_velocity_1d REAL,
                sell_velocity_1d REAL,
                buy_velocity_7d REAL,
                sell_velocity_7d REAL,
                buy_velocity_30d REAL,
                sell_velocity_30d REAL,
                buy_sold_1d INTEGER,
                sell_sold_1d INTEGER,
                buy_sold_7d INTEGER,
                sell_sold_7d INTEGER,
                buy_sold_30d INTEGER,
                sell_sold_30d INTEGER,
                buy_competition_ratio REAL,
                sell_competition_ratio REAL,
                competition_gold REAL,
                competition_tiers INTEGER,
                price_pressure REAL,
                buy_price_min_yesterday INTEGER,
                sell_price_max_yesterday INTEGER,
                flip_score REAL,
                price_updated TEXT,
                velocity_updated TEXT
            )
        """
        )

        existing_columns = {
            row[1]
            for row in cursor.execute("PRAGMA table_info(items)").fetchall()
        }
        if "flip_score" not in existing_columns:
            cursor.execute("ALTER TABLE items ADD COLUMN flip_score REAL")

        conn.commit()
        conn.close()

    def clear_all_items(self) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM items")
        conn.commit()
        conn.close()

    def upsert_items(self, items: list[ItemPrice]) -> None:
        if not items:
            return

        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()

        for item in items:
            cursor.execute(
                """
                INSERT INTO items
                    (id, name, buy_price, sell_price, buy_quantity,
                     sell_quantity, vendor_value, price_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    buy_price = excluded.buy_price,
                    sell_price = excluded.sell_price,
                    buy_quantity = excluded.buy_quantity,
                    sell_quantity = excluded.sell_quantity,
                    vendor_value = COALESCE(excluded.vendor_value, items.vendor_value),
                    price_updated = excluded.price_updated
                """,
                (
                    item.id,
                    item.name,
                    item.buy_price,
                    item.sell_price,
                    item.buy_quantity,
                    item.sell_quantity,
                    item.vendor_value,
                    now,
                ),
            )

        conn.commit()
        conn.close()

    def update_item_history(
        self,
        item_id: int,
        buy_sold_1d: int,
        sell_sold_1d: int,
        buy_sold_7d: int,
        sell_sold_7d: int,
        buy_sold_30d: int,
        sell_sold_30d: int,
        buy_competition_ratio: float,
        sell_competition_ratio: float,
        price_pressure: float,
        buy_price_min_yesterday: Optional[int],
        sell_price_max_yesterday: Optional[int],
    ) -> None:
        self.update_item_history_bulk(
            [
                (
                    item_id,
                    buy_sold_1d,
                    sell_sold_1d,
                    buy_sold_7d,
                    sell_sold_7d,
                    buy_sold_30d,
                    sell_sold_30d,
                    buy_competition_ratio,
                    sell_competition_ratio,
                    price_pressure,
                    buy_price_min_yesterday,
                    sell_price_max_yesterday,
                )
            ]
        )

    def update_item_history_bulk(self, updates: list[HistoryUpdateRow]) -> None:
        if not updates:
            return

        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()

        rows = [
            (
                buy_sold_1d,
                sell_sold_1d,
                buy_sold_7d,
                sell_sold_7d,
                buy_sold_30d,
                sell_sold_30d,
                buy_competition_ratio,
                sell_competition_ratio,
                price_pressure,
                buy_price_min_yesterday,
                sell_price_max_yesterday,
                now,
                item_id,
            )
            for (
                item_id,
                buy_sold_1d,
                sell_sold_1d,
                buy_sold_7d,
                sell_sold_7d,
                buy_sold_30d,
                sell_sold_30d,
                buy_competition_ratio,
                sell_competition_ratio,
                price_pressure,
                buy_price_min_yesterday,
                sell_price_max_yesterday,
            ) in updates
        ]

        cursor.executemany(
            """
            UPDATE items SET
                buy_sold_1d = ?,
                sell_sold_1d = ?,
                buy_sold_7d = ?,
                sell_sold_7d = ?,
                buy_sold_30d = ?,
                sell_sold_30d = ?,
                buy_competition_ratio = ?,
                sell_competition_ratio = ?,
                price_pressure = ?,
                buy_price_min_yesterday = ?,
                sell_price_max_yesterday = ?,
                velocity_updated = ?
            WHERE id = ?
            """,
            rows,
        )

        conn.commit()
        conn.close()

    def recompute_derived_metrics(self) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                id,
                buy_price,
                sell_price,
                vendor_value,
                buy_sold_1d,
                sell_sold_1d,
                buy_sold_7d,
                sell_sold_7d,
                buy_sold_30d,
                sell_sold_30d
            FROM items
            """
        )
        rows = cursor.fetchall()

        updates = []
        for row in rows:
            buy_price = row["buy_price"] or 0
            sell_price = row["sell_price"] or 0

            buy_sold_1d = row["buy_sold_1d"] or 0
            sell_sold_1d = row["sell_sold_1d"] or 0
            buy_sold_7d = row["buy_sold_7d"] or 0
            sell_sold_7d = row["sell_sold_7d"] or 0
            buy_sold_30d = row["buy_sold_30d"] or 0
            sell_sold_30d = row["sell_sold_30d"] or 0

            buy_velocity_1d = (buy_sold_1d * buy_price) / 10000.0
            sell_velocity_1d = (sell_sold_1d * sell_price) / 10000.0
            buy_velocity_7d = ((buy_sold_7d / 7.0) * buy_price) / 10000.0
            sell_velocity_7d = ((sell_sold_7d / 7.0) * sell_price) / 10000.0
            buy_velocity_30d = ((buy_sold_30d / 30.0) * buy_price) / 10000.0
            sell_velocity_30d = ((sell_sold_30d / 30.0) * sell_price) / 10000.0

            flip_score = 0.0
            if buy_price > 0 and sell_price > 0:
                percent_profit = calc_percent_profit(
                    buy_price,
                    sell_price,
                    row["vendor_value"],
                )
                flip_score = calc_flip_score(
                    buy_sold_1d,
                    sell_sold_1d,
                    buy_price,
                    percent_profit,
                )

            updates.append(
                (
                    buy_velocity_1d,
                    sell_velocity_1d,
                    buy_velocity_7d,
                    sell_velocity_7d,
                    buy_velocity_30d,
                    sell_velocity_30d,
                    flip_score,
                    row["id"],
                )
            )

        cursor.executemany(
            """
            UPDATE items SET
                buy_velocity_1d = ?,
                sell_velocity_1d = ?,
                buy_velocity_7d = ?,
                sell_velocity_7d = ?,
                buy_velocity_30d = ?,
                sell_velocity_30d = ?,
                flip_score = ?
            WHERE id = ?
            """,
            updates,
        )

        conn.commit()
        conn.close()

    def update_item_order_book(
        self,
        item_id: int,
        competition_gold: float,
        competition_tiers: int,
    ) -> None:
        self.update_item_order_book_bulk([(item_id, competition_gold, competition_tiers)])

    def update_item_order_book_bulk(self, updates: list[OrderBookUpdateRow]) -> None:
        if not updates:
            return

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.executemany(
            """
            UPDATE items SET
                competition_gold = ?,
                competition_tiers = ?
            WHERE id = ?
            """,
            [
                (competition_gold, competition_tiers, item_id)
                for item_id, competition_gold, competition_tiers in updates
            ],
        )

        conn.commit()
        conn.close()

    def get_items_missing_vendor_value(self) -> list[Item]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM items WHERE vendor_value IS NULL")
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_item(row) for row in rows]

    def update_vendor_values(self, vendor_values: dict[int, int]) -> None:
        if not vendor_values:
            return

        conn = self._get_connection()
        cursor = conn.cursor()

        for item_id, vendor_value in vendor_values.items():
            cursor.execute(
                "UPDATE items SET vendor_value = ? WHERE id = ?",
                (vendor_value, item_id),
            )

        conn.commit()
        conn.close()

    def get_all_items(self) -> list[Item]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM items")
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_item(row) for row in rows]

    def get_item(self, item_id: int) -> Optional[Item]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_item(row)
        return None

    def search_items(self, query: str) -> list[Item]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM items WHERE name LIKE ? LIMIT 20",
            (f"%{query}%",),
        )
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_item(row) for row in rows]

    def get_items_with_velocity(self) -> list[Item]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM items
            WHERE buy_price > 0
            AND sell_price > 0
            AND buy_sold_1d > 0
            AND sell_sold_1d > 0
            """
        )
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_item(row) for row in rows]

    def get_top_profit_candidates(self, limit: int = 500) -> list[Item]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM items
            WHERE buy_price IS NOT NULL
            AND sell_price IS NOT NULL
            AND buy_price > 0
            AND sell_price > 0
            AND sell_price > buy_price
            ORDER BY COALESCE(flip_score, 0) DESC, (sell_price - buy_price) DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_item(row) for row in rows]

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> Item:
        return Item(
            id=row["id"],
            name=row["name"],
            buy_price=row["buy_price"],
            sell_price=row["sell_price"],
            buy_quantity=row["buy_quantity"],
            sell_quantity=row["sell_quantity"],
            vendor_value=row["vendor_value"],
            buy_velocity_1d=row["buy_velocity_1d"],
            sell_velocity_1d=row["sell_velocity_1d"],
            buy_velocity_7d=row["buy_velocity_7d"],
            sell_velocity_7d=row["sell_velocity_7d"],
            buy_velocity_30d=row["buy_velocity_30d"],
            sell_velocity_30d=row["sell_velocity_30d"],
            buy_sold_1d=row["buy_sold_1d"],
            sell_sold_1d=row["sell_sold_1d"],
            buy_sold_7d=row["buy_sold_7d"],
            sell_sold_7d=row["sell_sold_7d"],
            buy_sold_30d=row["buy_sold_30d"],
            sell_sold_30d=row["sell_sold_30d"],
            buy_competition_ratio=row["buy_competition_ratio"],
            sell_competition_ratio=row["sell_competition_ratio"],
            competition_gold=row["competition_gold"],
            competition_tiers=row["competition_tiers"],
            price_pressure=row["price_pressure"],
            buy_price_min_yesterday=row["buy_price_min_yesterday"],
            sell_price_max_yesterday=row["sell_price_max_yesterday"],
            flip_score=row["flip_score"],
            price_updated=row["price_updated"],
            velocity_updated=row["velocity_updated"],
        )
