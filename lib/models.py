from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Item:
    id: int
    name: str
    buy_price: Optional[int] = None
    sell_price: Optional[int] = None
    buy_quantity: Optional[int] = None
    sell_quantity: Optional[int] = None
    vendor_value: Optional[int] = None
    buy_velocity_1d: Optional[float] = None
    sell_velocity_1d: Optional[float] = None
    buy_velocity_7d: Optional[float] = None
    sell_velocity_7d: Optional[float] = None
    buy_velocity_30d: Optional[float] = None
    sell_velocity_30d: Optional[float] = None
    buy_sold_1d: Optional[int] = None
    sell_sold_1d: Optional[int] = None
    buy_sold_7d: Optional[int] = None
    sell_sold_7d: Optional[int] = None
    buy_sold_30d: Optional[int] = None
    sell_sold_30d: Optional[int] = None
    buy_competition_ratio: Optional[float] = None
    sell_competition_ratio: Optional[float] = None
    competition_gold: Optional[float] = None
    competition_tiers: Optional[int] = None
    price_pressure: Optional[float] = None
    buy_price_min_yesterday: Optional[int] = None
    sell_price_max_yesterday: Optional[int] = None
    listed_ratio: Optional[float] = None
    delisted_ratio: Optional[float] = None
    spread_percent: Optional[float] = None
    price_updated: Optional[str] = None
    velocity_updated: Optional[str] = None


@dataclass
class FlipResult:
    item: Item
    percent_profit: float
    flip_score: float
    flip_velocity: float = 0.0

    @property
    def id(self) -> int:
        return self.item.id

    @property
    def name(self) -> str:
        return self.item.name

    @property
    def buy_price(self) -> Optional[int]:
        return self.item.buy_price

    @property
    def sell_price(self) -> Optional[int]:
        return self.item.sell_price


@dataclass
class HistoryEntry:
    date: str
    buy_sold: int = 0
    sell_sold: int = 0
    buy_value: int = 0
    sell_value: int = 0
    buy_listed: int = 0
    sell_listed: int = 0
    buy_delisted: int = 0
    sell_delisted: int = 0
    buy_price_avg: Optional[float] = None
    buy_price_min: Optional[int] = None
    buy_price_max: Optional[int] = None
    buy_price_stdev: Optional[float] = None
    sell_price_avg: Optional[float] = None
    sell_price_min: Optional[int] = None
    sell_price_max: Optional[int] = None
    sell_price_stdev: Optional[float] = None
    buy_quantity_avg: Optional[float] = None
    sell_quantity_avg: Optional[float] = None
    count: int = 0


@dataclass
class OrderBook:
    item_id: int
    buys: list[dict] = field(default_factory=list)
    sells: list[dict] = field(default_factory=list)

    def get_competition_metrics(
        self, buy_price_floor: Optional[int] = None
    ) -> tuple[float, int]:
        if buy_price_floor is None or not self.buys:
            return 0.0, 0

        competition_gold = 0.0
        price_tiers = 0

        for order in self.buys:
            price = order.get("unit_price", 0)
            quantity = order.get("quantity", 0)
            if price > buy_price_floor:
                competition_gold += (price * quantity) / 10000.0
                price_tiers += 1

        return competition_gold, price_tiers

    def get_sell_competition_metrics(
        self, sell_price_ceiling: Optional[int] = None
    ) -> tuple[float, int]:
        if sell_price_ceiling is None or not self.sells:
            return 0.0, 0

        competition_gold = 0.0
        price_tiers = 0

        for order in self.sells:
            price = order.get("unit_price", 0)
            quantity = order.get("quantity", 0)
            if price < sell_price_ceiling and price > 0:
                competition_gold += (price * quantity) / 10000.0
                price_tiers += 1

        return competition_gold, price_tiers


@dataclass
class ItemPrice:
    id: int
    name: str
    buy_price: Optional[int] = None
    sell_price: Optional[int] = None
    buy_quantity: Optional[int] = None
    sell_quantity: Optional[int] = None
    vendor_value: Optional[int] = None
    buy_velocity_1d: Optional[float] = None
    sell_velocity_1d: Optional[float] = None
    buy_velocity_7d: Optional[float] = None
    sell_velocity_7d: Optional[float] = None
    buy_velocity_30d: Optional[float] = None
    sell_velocity_30d: Optional[float] = None
    buy_sold_1d: Optional[int] = None
    sell_sold_1d: Optional[int] = None
    buy_sold_7d: Optional[int] = None
    sell_sold_7d: Optional[int] = None
    buy_sold_30d: Optional[int] = None
    sell_sold_30d: Optional[int] = None
