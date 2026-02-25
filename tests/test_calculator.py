import pytest

from lib.calculator import (
    calc_competition_ratio,
    calc_flip_score,
    calc_percent_profit,
    calc_price_pressure,
    calc_velocity,
    calculate_flip_result,
)
from lib.models import HistoryEntry, Item, OrderBook


class TestCalcPercentProfit:
    def test_basic_profit(self):
        profit = calc_percent_profit(100, 150)
        assert profit > 0
        assert profit == pytest.approx(25.742, rel=0.01)

    def test_no_profit(self):
        profit = calc_percent_profit(100, 100)
        assert profit == 0.0

    def test_negative_profit(self):
        profit = calc_percent_profit(100, 80)
        assert profit == 0.0

    def test_zero_prices(self):
        assert calc_percent_profit(0, 100) == 0.0
        assert calc_percent_profit(100, 0) == 0.0
        assert calc_percent_profit(0, 0) == 0.0

    def test_high_profit(self):
        profit = calc_percent_profit(1000, 2000)
        assert profit > 0
        assert profit == pytest.approx(69.745, rel=0.01)


class TestCalcVelocity:
    def test_empty_history(self):
        velocities = calc_velocity([])
        assert velocities == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_single_day(self):
        history = [HistoryEntry(date="2024-01-01", buy_value=100000, sell_value=200000)]
        velocities = calc_velocity(history)

        assert velocities[0] == 10.0
        assert velocities[1] == 20.0

    def test_multiple_days(self):
        history = [
            HistoryEntry(date="2024-01-03", buy_value=100000, sell_value=200000),
            HistoryEntry(date="2024-01-02", buy_value=200000, sell_value=300000),
            HistoryEntry(date="2024-01-01", buy_value=300000, sell_value=400000),
        ]
        velocities = calc_velocity(history)

        assert velocities[0] == 10.0
        assert velocities[1] == 20.0

        avg_7d_buy = (100000 + 200000 + 300000) / 3 / 10000
        assert velocities[2] == pytest.approx(avg_7d_buy, rel=0.01)


class TestCalcCompetitionRatio:
    def test_empty_history(self):
        buy_ratio, sell_ratio = calc_competition_ratio([])
        assert buy_ratio == 0.0
        assert sell_ratio == 0.0

    def test_balanced_market(self):
        history = [
            HistoryEntry(
                date="2024-01-01",
                buy_listed=100,
                buy_sold=100,
                sell_listed=100,
                sell_sold=100,
            )
        ]
        buy_ratio, sell_ratio = calc_competition_ratio(history)
        assert buy_ratio == 1.0
        assert sell_ratio == 1.0

    def test_competitive_market(self):
        history = [
            HistoryEntry(
                date="2024-01-01",
                buy_listed=500,
                buy_sold=100,
                sell_listed=600,
                sell_sold=200,
            )
        ]
        buy_ratio, sell_ratio = calc_competition_ratio(history)
        assert buy_ratio == 5.0
        assert sell_ratio == 3.0


class TestCalcPricePressure:
    def test_empty_history(self):
        pressure = calc_price_pressure([])
        assert pressure == 0.0

    def test_single_day_history(self):
        history = [HistoryEntry(date="2024-01-01")]
        pressure = calc_price_pressure(history)
        assert pressure == 0.0

    def test_compression_positive(self):
        history = [
            HistoryEntry(
                date="2024-01-02",
                buy_price_avg=100,
                sell_price_avg=120,
                buy_delisted=10,
                sell_delisted=10,
                buy_sold=100,
                sell_sold=100,
            ),
            HistoryEntry(
                date="2024-01-01",
                buy_price_avg=95,
                sell_price_avg=130,
            ),
        ]
        pressure = calc_price_pressure(history)
        assert pressure > 0


class TestCalcFlipScore:
    def test_basic_calculation(self):
        # min(buy_sold, sell_sold) * buy_price * ROI
        # min(100, 50) * 1000 * 0.10 = 50 * 1000 * 0.10 = 5000
        score = calc_flip_score(100, 50, 1000, 10.0)
        assert score == 5000.0

    def test_negative_profit(self):
        score = calc_flip_score(100, 50, 1000, -10.0)
        assert score == 0.0

    def test_zero_quantity(self):
        score = calc_flip_score(0, 50, 1000, 10.0)
        assert score == 0.0

    def test_quantity_of_sold_not_listings(self):
        # This tests that we're using historical sold qty, not listing qty
        # Example: 10 items sold in history, buy price 100g, 20% profit
        # flip_score = 10 * 100 * 0.20 = 200
        score = calc_flip_score(10, 20, 10000, 20.0)
        assert score == 20000.0  # 10 * 10000 * 0.20 = 20000


class TestCalculateFlipResult:
    def test_valid_item(self):
        item = Item(
            id=1,
            name="Test Item",
            buy_price=100,
            sell_price=150,
            buy_quantity=100,
            sell_quantity=100,
            buy_velocity_1d=10.0,
            sell_velocity_1d=15.0,
            buy_sold_1d=10,
            sell_sold_1d=15,
        )
        result = calculate_flip_result(item, days=1)

        assert result is not None
        assert result.percent_profit > 0
        assert result.flip_velocity == 10.0
        assert result.flip_score > 0

    def test_missing_prices(self):
        item = Item(id=1, name="Test Item", buy_velocity_1d=10.0, sell_velocity_1d=15.0)
        result = calculate_flip_result(item, days=1)
        assert result is None

    def test_missing_velocity(self):
        item = Item(id=1, name="Test Item", buy_price=100, sell_price=150)
        result = calculate_flip_result(item, days=1)
        assert result is None

    def test_different_timeframes(self):
        item = Item(
            id=1,
            name="Test Item",
            buy_price=100,
            sell_price=150,
            buy_quantity=100,
            sell_quantity=100,
            buy_velocity_1d=10.0,
            sell_velocity_1d=15.0,
            buy_velocity_7d=50.0,
            sell_velocity_7d=75.0,
            buy_velocity_30d=200.0,
            sell_velocity_30d=300.0,
            buy_sold_1d=10,
            sell_sold_1d=15,
            buy_sold_7d=50,
            sell_sold_7d=75,
            buy_sold_30d=200,
            sell_sold_30d=300,
        )

        result_1d = calculate_flip_result(item, days=1)
        result_7d = calculate_flip_result(item, days=7)
        result_30d = calculate_flip_result(item, days=30)

        assert result_1d.flip_velocity == 10.0
        assert result_7d.flip_velocity == 50.0
        assert result_30d.flip_velocity == 200.0


class TestOrderBook:
    def test_competition_metrics_no_floor(self):
        order_book = OrderBook(
            item_id=1,
            buys=[
                {"unit_price": 100, "quantity": 10},
                {"unit_price": 105, "quantity": 20},
            ],
        )
        gold, tiers = order_book.get_competition_metrics(None)
        assert gold == 0.0
        assert tiers == 0

    def test_competition_metrics_with_floor(self):
        order_book = OrderBook(
            item_id=1,
            buys=[
                {"unit_price": 100, "quantity": 10},
                {"unit_price": 105, "quantity": 20},
                {"unit_price": 110, "quantity": 30},
            ],
        )
        gold, tiers = order_book.get_competition_metrics(100)

        assert tiers == 2

        expected_gold = (105 * 20 + 110 * 30) / 10000
        assert gold == pytest.approx(expected_gold, rel=0.01)
