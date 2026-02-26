import pytest

from lib.database import Database
from lib.models import ItemPrice


def test_update_item_history_bulk_and_recompute_updates_multiple_rows(tmp_path):
    db_path = tmp_path / "test_bulk_velocity.db"
    db = Database(str(db_path))
    db.upsert_items(
        [
            ItemPrice(id=1, name="Item 1", buy_price=100, sell_price=200),
            ItemPrice(id=2, name="Item 2", buy_price=150, sell_price=250),
        ]
    )

    updates = [
        (
            1,
            1,
            2,
            7,
            14,
            30,
            60,
            1.5,
            1.2,
            0.02,
            99,
            205,
        ),
        (
            2,
            3,
            4,
            8,
            15,
            31,
            61,
            2.5,
            2.2,
            -0.01,
            149,
            255,
        ),
    ]

    db.update_item_history_bulk(updates)
    db.recompute_derived_metrics()

    item_1 = db.get_item(1)
    item_2 = db.get_item(2)
    assert item_1 is not None
    assert item_2 is not None

    assert item_1.buy_velocity_1d == pytest.approx(0.01)
    assert item_1.sell_velocity_1d == pytest.approx(0.04)
    assert item_1.buy_sold_30d == 30
    assert item_1.buy_price_min_yesterday == 99
    assert item_1.sell_price_max_yesterday == 205
    assert item_1.flip_score > 0
    assert item_1.velocity_updated is not None

    assert item_2.buy_velocity_1d == pytest.approx(0.045)
    assert item_2.sell_velocity_1d == pytest.approx(0.1)
    assert item_2.buy_sold_30d == 31
    assert item_2.buy_price_min_yesterday == 149
    assert item_2.sell_price_max_yesterday == 255
    assert item_2.flip_score > 0
    assert item_2.velocity_updated is not None


def test_upsert_items_preserves_history_derived_metrics(tmp_path):
    db_path = tmp_path / "test_preserve_derived.db"
    db = Database(str(db_path))
    db.upsert_items([ItemPrice(id=1, name="Item 1", buy_price=100, sell_price=200)])
    db.update_item_history_bulk([(1, 5, 10, 35, 70, 150, 300, 1.0, 1.0, 0.0, 99, 205)])
    db.recompute_derived_metrics()

    before = db.get_item(1)
    assert before is not None
    assert before.buy_sold_1d == 5
    assert before.flip_score is not None and before.flip_score > 0

    db.upsert_items([ItemPrice(id=1, name="Item 1", buy_price=110, sell_price=220)])

    after = db.get_item(1)
    assert after is not None
    assert after.buy_sold_1d == 5
    assert after.flip_score == before.flip_score


def test_update_item_order_book_bulk_updates_multiple_rows(tmp_path):
    db_path = tmp_path / "test_bulk_orderbook.db"
    db = Database(str(db_path))
    db.upsert_items(
        [
            ItemPrice(id=1, name="Item 1", buy_price=100, sell_price=200),
            ItemPrice(id=2, name="Item 2", buy_price=150, sell_price=250),
        ]
    )

    db.update_item_order_book_bulk([(1, 120.5, 4), (2, 42.0, 2)])

    item_1 = db.get_item(1)
    item_2 = db.get_item(2)
    assert item_1 is not None
    assert item_2 is not None

    assert item_1.competition_gold == pytest.approx(120.5)
    assert item_1.competition_tiers == 4
    assert item_2.competition_gold == pytest.approx(42.0)
    assert item_2.competition_tiers == 2
