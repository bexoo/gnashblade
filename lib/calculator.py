from typing import Optional

from lib.models import FlipResult, HistoryEntry, Item, OrderBook


def calc_percent_profit(
    buy_price: int, sell_price: int, vendor_value: Optional[int] = None
) -> float:
    if buy_price <= 0 or sell_price <= 0:
        return 0.0

    cost = buy_price + 1

    # Check if buy price is at or below vendor value (impossible listing)
    if vendor_value is not None and buy_price <= vendor_value:
        return 0.0

    # Minimum Trading Post fee is 1 copper for both listing (5%) and exchange (10%) fees
    listing_fee = max(1, int(sell_price * 0.05))
    exchange_fee = max(1, int(sell_price * 0.10))
    revenue = sell_price - 1 - listing_fee - exchange_fee

    if revenue <= cost:
        return 0.0

    # Also check if vendoring is more profitable than selling on the TP
    if vendor_value is not None and revenue <= vendor_value:
        return 0.0

    return (revenue - cost) / cost * 100


def calc_velocity(
    history: list[HistoryEntry],
) -> tuple[float, float, float, float, float, float]:
    if not history:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    buy_values = [h.buy_value for h in history if h.buy_value]
    sell_values = [h.sell_value for h in history if h.sell_value]

    buy_velocity_1d = buy_values[0] / 10000.0 if buy_values else 0.0
    sell_velocity_1d = sell_values[0] / 10000.0 if sell_values else 0.0

    buy_velocity_7d = (
        sum(buy_values[:7]) / min(7, len(buy_values)) / 10000.0 if buy_values else 0.0
    )
    sell_velocity_7d = (
        sum(sell_values[:7]) / min(7, len(sell_values)) / 10000.0
        if sell_values
        else 0.0
    )

    buy_velocity_30d = (
        sum(buy_values[:30]) / min(30, len(buy_values)) / 10000.0 if buy_values else 0.0
    )
    sell_velocity_30d = (
        sum(sell_values[:30]) / min(30, len(sell_values)) / 10000.0
        if sell_values
        else 0.0
    )

    return (
        buy_velocity_1d,
        sell_velocity_1d,
        buy_velocity_7d,
        sell_velocity_7d,
        buy_velocity_30d,
        sell_velocity_30d,
    )


def calc_quantity_sold(
    history: list[HistoryEntry],
) -> tuple[int, int, int, int, int, int]:
    if not history:
        return 0, 0, 0, 0, 0, 0

    buy_quantities = [h.buy_sold for h in history if h.buy_sold]
    sell_quantities = [h.sell_sold for h in history if h.sell_sold]

    buy_sold_1d = buy_quantities[0] if buy_quantities else 0
    sell_sold_1d = sell_quantities[0] if sell_quantities else 0

    buy_sold_7d = sum(buy_quantities[:7]) if buy_quantities else 0
    sell_sold_7d = sum(sell_quantities[:7]) if sell_quantities else 0

    buy_sold_30d = sum(buy_quantities[:30]) if buy_quantities else 0
    sell_sold_30d = sum(sell_quantities[:30]) if sell_quantities else 0

    return (
        buy_sold_1d,
        sell_sold_1d,
        buy_sold_7d,
        sell_sold_7d,
        buy_sold_30d,
        sell_sold_30d,
    )


def calc_competition_ratio(
    history: list[HistoryEntry],
) -> tuple[float, float]:
    if not history:
        return 0.0, 0.0

    entry = history[0]

    buy_ratio = (
        float("inf") if entry.buy_sold == 0 else entry.buy_listed / entry.buy_sold
    )

    sell_ratio = (
        float("inf") if entry.sell_sold == 0 else entry.sell_listed / entry.sell_sold
    )

    return buy_ratio, sell_ratio


def calc_price_pressure(
    history: list[HistoryEntry],
) -> float:
    if len(history) < 2:
        return 0.0

    today = history[0]
    yesterday = history[1]

    today_buy_avg = today.buy_price_avg or 0
    today_sell_avg = today.sell_price_avg or 0
    yesterday_buy_avg = yesterday.buy_price_avg or 0
    yesterday_sell_avg = yesterday.sell_price_avg or 0

    if today_buy_avg <= 0 or today_sell_avg <= 0:
        return 0.0
    if yesterday_buy_avg <= 0 or yesterday_sell_avg <= 0:
        return 0.0

    spread_today = today_sell_avg - today_buy_avg
    spread_yesterday = yesterday_sell_avg - yesterday_buy_avg

    if spread_yesterday <= 0:
        return 0.0

    spread_compression = (spread_yesterday - spread_today) / spread_yesterday

    total_sold = today.buy_sold + today.sell_sold
    total_delisted = today.buy_delisted + today.sell_delisted
    delisted_ratio = total_delisted / total_sold if total_sold > 0 else 0.0

    return spread_compression + delisted_ratio


def calc_order_book_competition(
    order_book: OrderBook,
    buy_price_floor: Optional[int] = None,
    sell_price_ceiling: Optional[int] = None,
) -> tuple[float, int, float, int]:
    buy_competition_gold, buy_tiers = order_book.get_competition_metrics(
        buy_price_floor
    )
    sell_competition_gold, sell_tiers = order_book.get_sell_competition_metrics(
        sell_price_ceiling
    )

    return buy_competition_gold, buy_tiers, sell_competition_gold, sell_tiers


def calc_flip_score(
    buy_sold_qty: int,
    sell_sold_qty: int,
    buy_price: int,
    percent_profit: float,
) -> float:
    if percent_profit <= 0:
        return 0.0

    quantity = min(buy_sold_qty, sell_sold_qty)
    return quantity * buy_price * (percent_profit / 100)


def get_yesterday_floor_prices(
    history: list[HistoryEntry],
) -> tuple[Optional[int], Optional[int]]:
    if len(history) < 2:
        return None, None

    yesterday = history[1]
    return yesterday.buy_price_min, yesterday.sell_price_max


def calculate_flip_result(
    item: Item,
    days: int = 1,
) -> Optional[FlipResult]:
    if (
        item.buy_price is None
        or item.sell_price is None
        or item.buy_quantity is None
        or item.sell_quantity is None
    ):
        return None
    if item.buy_price <= 0 or item.sell_price <= 0:
        return None

    # Filter out items with no buy or sell orders
    if item.buy_quantity == 0 or item.sell_quantity == 0:
        return None

    # Filter out unfillable orders (below vendor value)
    if item.vendor_value is not None and item.buy_price <= item.vendor_value:
        return None

    percent_profit = calc_percent_profit(
        item.buy_price, item.sell_price, item.vendor_value
    )
    if percent_profit <= 0:
        return None

    if days == 1:
        buy_vel = item.buy_velocity_1d or 0.0
        sell_vel = item.sell_velocity_1d or 0.0
        buy_sold = item.buy_sold_1d or 0
        sell_sold = item.sell_sold_1d or 0
    elif days == 7:
        buy_vel = item.buy_velocity_7d or 0.0
        sell_vel = item.sell_velocity_7d or 0.0
        buy_sold = item.buy_sold_7d or 0
        sell_sold = item.sell_sold_7d or 0
    else:
        buy_vel = item.buy_velocity_30d or 0.0
        sell_vel = item.sell_velocity_30d or 0.0
        buy_sold = item.buy_sold_30d or 0
        sell_sold = item.sell_sold_30d or 0

    if buy_vel <= 0 or sell_vel <= 0:
        return None

    flip_velocity = min(buy_vel, sell_vel)
    flip_score = calc_flip_score(
        buy_sold,
        sell_sold,
        item.buy_price,
        percent_profit,
    )

    if flip_score <= 0:
        return None

    return FlipResult(
        item=item,
        percent_profit=percent_profit,
        flip_velocity=flip_velocity,
        flip_score=flip_score,
    )
