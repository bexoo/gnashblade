import pytest

from lib.database import Database
from lib.models import ItemPrice


def test_update_item_velocity_bulk_updates_multiple_rows(tmp_path):
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
            10.0,
            20.0,
            70.0,
            140.0,
            300.0,
            600.0,
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
            11.0,
            21.0,
            71.0,
            141.0,
            301.0,
            601.0,
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

    db.update_item_velocity_bulk(updates)

    item_1 = db.get_item(1)
    item_2 = db.get_item(2)
    assert item_1 is not None
    assert item_2 is not None

    assert item_1.buy_velocity_1d == pytest.approx(10.0)
    assert item_1.sell_velocity_1d == pytest.approx(20.0)
    assert item_1.buy_sold_30d == 30
    assert item_1.buy_price_min_yesterday == 99
    assert item_1.sell_price_max_yesterday == 205
    assert item_1.velocity_updated is not None

    assert item_2.buy_velocity_1d == pytest.approx(11.0)
    assert item_2.sell_velocity_1d == pytest.approx(21.0)
    assert item_2.buy_sold_30d == 31
    assert item_2.buy_price_min_yesterday == 149
    assert item_2.sell_price_max_yesterday == 255
    assert item_2.velocity_updated is not None


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
