#!/usr/bin/env python3
import argparse
import asyncio
import sys
import time
from typing import Optional

from lib.api import DataWars2Client, GW2Client
from lib.calculator import (
    calc_competition_ratio,
    calc_order_book_competition,
    calc_price_pressure,
    calc_quantity_sold,
    calculate_flip_result,
    get_yesterday_floor_prices,
)
from lib.database import Database

VERBOSE = False
SILENT = False


def log(message: str) -> None:
    if not SILENT:
        print(message)


def vlog(message: str) -> None:
    if VERBOSE and not SILENT:
        print(message)


def format_gold(copper: int) -> str:
    gold = copper / 10000
    silver = (copper % 10000) / 100
    if gold >= 1000:
        return f"{gold / 1000:.1f}k"
    if gold >= 1:
        return f"{gold:.1f}g"
    if silver >= 1:
        return f"{silver:.0f}s"
    return f"{copper}c"


def format_gold_short(copper: int) -> str:
    gold = copper / 10000
    if gold >= 1000:
        return f"{gold / 1000:.1f}k"
    return f"{gold:.0f}"


def format_velocity(velocity: float) -> str:
    if velocity >= 1000:
        return f"{velocity / 1000:.1f}k"
    if velocity < 10 and velocity != 0:
        return f"{velocity:.1f}"
    return f"{velocity:.0f}"


def format_competition_ratio(ratio: float) -> str:
    if ratio == float("inf"):
        return "inf"
    return f"{ratio:.1f}x"


def format_gsc(copper: int) -> str:
    """Format copper as Xg Ys Zc"""
    gold = copper // 10000
    silver = (copper % 10000) // 100
    cents = copper % 100
    if gold > 0:
        return f"{gold}g{silver:02d}s{cents:02d}c"
    elif silver > 0:
        return f"{silver}s{cents:02d}c"
    else:
        return f"{cents}c"


def format_pressure(pressure: float) -> str:
    if pressure > 0:
        return f"+{pressure * 100:.1f}%"
    return f"{pressure * 100:.1f}%"


def _log_stage_timing(stage_name: str, started_at: float) -> None:
    elapsed = time.perf_counter() - started_at
    vlog(f"[timing] {stage_name}: {elapsed:.2f}s")


async def _run_update_cycle(
    db: Database,
    dw2: DataWars2Client,
    gw2: GW2Client,
    full: bool,
    deep_refresh: bool,
    history_workers: int,
    orderbook_workers: int,
    fetch_order_books: bool,
) -> None:
    cycle_started = time.perf_counter()

    prices_started = time.perf_counter()
    log("Fetching all item prices...")
    items = await dw2.fetch_all_items()
    vlog(f"Found {len(items)} items")
    _log_stage_timing("fetch prices", prices_started)

    upsert_started = time.perf_counter()
    log("Updating database...")
    db.upsert_items(items)
    _log_stage_timing("upsert prices", upsert_started)

    vendor_started = time.perf_counter()
    vlog("Checking for missing vendor values...")
    missing_items = db.get_items_missing_vendor_value()
    if missing_items:
        vlog(f"Fetching vendor values for {len(missing_items)} items...")
        item_ids_missing = [item.id for item in missing_items]
        vendor_data = await gw2.fetch_items_batch(item_ids_missing)
        vendor_values = {
            item_id: data.get("vendor_value", 0)
            for item_id, data in vendor_data.items()
        }
        if vendor_values:
            vlog(f"Updating {len(vendor_values)} vendor values in database...")
            db.update_vendor_values(vendor_values)
    _log_stage_timing("vendor value refresh", vendor_started)

    if not deep_refresh:
        derive_started = time.perf_counter()
        log("Recomputing derived metrics from stored quantities...")
        db.recompute_derived_metrics()
        _log_stage_timing("recompute derived metrics", derive_started)
        log("Skipping deep refresh (history/order books) this cycle.")
        _log_stage_timing("total update cycle", cycle_started)
        return

    candidate_started = time.perf_counter()
    if full:
        log("Full update: fetching history for all items with valid prices...")
        candidates = db.get_top_profit_candidates(limit=999999)
    else:
        vlog("Filtering for top profit candidates...")
        candidates = db.get_top_profit_candidates(limit=500)
    _log_stage_timing("load candidates", candidate_started)

    item_ids = [candidate.id for candidate in candidates]
    log(
        f"Fetching history for {len(candidates)} candidates "
        f"({max(1, history_workers)} concurrent)..."
    )
    history_started = time.perf_counter()
    history_data = await dw2.fetch_history_batch(
        item_ids,
        days=30,
        max_concurrent=history_workers,
    )
    _log_stage_timing("fetch history", history_started)

    log("Calculating quantity and competition metrics...")
    calc_started = time.perf_counter()
    history_updates = []
    floor_price_map: dict[int, tuple[int, Optional[int]]] = {}
    for item_id, history in history_data.items():
        if not history:
            continue

        quantities = calc_quantity_sold(history)
        buy_ratio, sell_ratio = calc_competition_ratio(history)
        pressure = calc_price_pressure(history)
        buy_floor, sell_ceil = get_yesterday_floor_prices(history)

        history_updates.append(
            (
                item_id,
                quantities[0],
                quantities[1],
                quantities[2],
                quantities[3],
                quantities[4],
                quantities[5],
                buy_ratio,
                sell_ratio,
                pressure,
                buy_floor,
                sell_ceil,
            )
        )

        if buy_floor and buy_floor > 0:
            floor_price_map[item_id] = (buy_floor, sell_ceil)
    _log_stage_timing("calculate velocity metrics", calc_started)

    history_write_started = time.perf_counter()
    db.update_item_history_bulk(history_updates)
    _log_stage_timing("write history metrics", history_write_started)

    derive_started = time.perf_counter()
    log("Recomputing derived metrics from stored quantities...")
    db.recompute_derived_metrics()
    _log_stage_timing("recompute derived metrics", derive_started)

    order_book_item_ids = list(floor_price_map.keys())
    if fetch_order_books:
        log(
            f"Fetching order books for {len(order_book_item_ids)} candidates "
            f"({max(1, orderbook_workers)} concurrent)..."
        )
        order_book_fetch_started = time.perf_counter()
        order_books = await gw2.fetch_order_books_batch(
            order_book_item_ids,
            max_concurrent=orderbook_workers,
        )
        _log_stage_timing("fetch order books", order_book_fetch_started)

        order_book_calc_started = time.perf_counter()
        order_book_updates = []
        for item_id, order_book in order_books.items():
            buy_floor, sell_ceil = floor_price_map[item_id]
            buy_gold, buy_tiers, _, _ = calc_order_book_competition(
                order_book,
                buy_floor,
                sell_ceil,
            )
            order_book_updates.append((item_id, buy_gold, buy_tiers))
        _log_stage_timing("calculate order book metrics", order_book_calc_started)

        order_book_write_started = time.perf_counter()
        db.update_item_order_book_bulk(order_book_updates)
        _log_stage_timing("write order book metrics", order_book_write_started)
    else:
        log("Skipping order book fetch (use --fetch-order-books to enable)")
        order_books = {}
    _log_stage_timing("total update cycle", cycle_started)


def cmd_update(args: argparse.Namespace) -> int:
    global VERBOSE, SILENT
    VERBOSE = args.verbose
    SILENT = args.silent

    db = Database()
    dw2 = DataWars2Client()
    gw2 = GW2Client()

    try:
        asyncio.run(
            _run_update_cycle(
                db=db,
                dw2=dw2,
                gw2=gw2,
                full=args.full,
                deep_refresh=True,
                history_workers=args.history_workers,
                orderbook_workers=args.orderbook_workers,
                fetch_order_books=args.fetch_order_books,
            )
        )
    finally:
        if dw2._client is not None:
            dw2._client = None
        if gw2._client is not None:
            gw2._client = None

    log("Update complete!")
    return 0


def cmd_flips(args: argparse.Namespace) -> int:
    db = Database()
    items = db.get_items_with_velocity()

    results = []
    for item in items:
        if item.sell_price and item.sell_price > args.max_price:
            continue

        # Filter by 7-day average daily quantity sold/bought
        avg_daily_sold = (item.sell_sold_7d or 0) / 7
        avg_daily_bought = (item.buy_sold_7d or 0) / 7
        if avg_daily_sold < args.min_sold:
            continue
        if avg_daily_bought < args.min_bought:
            continue

        result = calculate_flip_result(item, days=args.days)
        if result and result.flip_score > 0:
            if result.percent_profit >= args.min_profit:
                if args.max_profit is None or result.percent_profit <= args.max_profit:
                    results.append(result)

    results.sort(key=lambda r: r.flip_score, reverse=True)
    results = results[: args.limit]

    if not results:
        print("No profitable flips found. Try running 'update' first.")
        return 1

    print()
    print(f"{'=' * 140}")
    print(f"  TOP {len(results)} FLIP OPPORTUNITIES ({args.days}-day)")
    print(f"{'=' * 140}")
    print(
        f"  {'#':>3}  {'Item Name':<24}  {'Buy':>12}  {'Sell':>12}  {'Profit':>8}  "
        f"{'Velocity':>10}  {'Score':>10}  {'Competition'}"
    )
    print(f"{'-' * 140}")

    for i, result in enumerate(results, 1):
        item = result.item
        comp_ratio = item.buy_competition_ratio or 0
        comp_gold = item.competition_gold or 0
        comp_tiers = item.competition_tiers or 0
        pressure = item.price_pressure or 0

        vel_str = f"{format_velocity(result.flip_velocity)} g/d"
        score_gold = result.flip_score / 10000
        score_str = f"{format_velocity(score_gold)} g/d"

        comp_str = (
            f"{format_competition_ratio(comp_ratio)}  "
            f"{format_gold_short(int(comp_gold))}g  "
            f"{comp_tiers}t  {format_pressure(pressure)}"
        )

        name = item.name[:22] + ".." if len(item.name) > 24 else item.name
        buy_str = format_gsc(item.buy_price) if item.buy_price else "N/A"
        sell_str = format_gsc(item.sell_price) if item.sell_price else "N/A"

        print(
            f"  {i:>3}  {name:<24}  {buy_str:>12}  {sell_str:>12}  "
            f"{result.percent_profit:>7.1f}%  {vel_str:>10}  {score_str:>10}  {comp_str}"
        )

    print(f"{'=' * 140}")
    print()
    max_p = f"{args.max_profit}%" if args.max_profit is not None else "None"
    print(
        f"  Filters: days={args.days}, min_profit={args.min_profit}%, "
        f"max_profit={max_p}, max_price={format_gold(args.max_price)}, "
        f"min_sold={args.min_sold}, min_bought={args.min_bought}, limit={args.limit}"
    )
    print()

    return 0


def cmd_item(args: argparse.Namespace) -> int:
    query = args.query
    db = Database()
    gw2 = GW2Client()
    datawars = DataWars2Client()

    # Try to parse as integer first (item ID)
    try:
        item_id = int(query)
        item = db.get_item(item_id)
        if item:
            items = [item]
        else:
            print(
                f"Item with ID {item_id} not found in database. Try running 'update' first."
            )
            asyncio.run(gw2.close())
            asyncio.run(datawars.close())
            return 1
    except ValueError:
        # Search by name
        items = db.search_items(query)
        if not items:
            print(f"No items found matching '{query}'. Try a different search term.")
            asyncio.run(gw2.close())
            asyncio.run(datawars.close())
            return 1
        if len(items) > 1:
            print(f"Multiple matches found for '{query}':\n")
            for i, item in enumerate(items, 1):
                print(f"  {i}. {item.name} (ID: {item.id})")
            print("\nRun with a more specific query or use the ID.")
            asyncio.run(gw2.close())
            asyncio.run(datawars.close())
            return 0

    item = items[0]
    order_book = None

    # Fetch fresh history if requested
    if args.history:
        print("Fetching fresh history data...")
        history = asyncio.run(datawars.fetch_history(item.id, days=30))
        if history:
            latest = history[0]
            item.buy_velocity_1d = float(latest.buy_sold)
            item.sell_velocity_1d = float(latest.sell_sold)

    # Calculate flip metrics
    flip_result = calculate_flip_result(item, days=1)
    flip_result_7d = calculate_flip_result(item, days=7)
    flip_result_30d = calculate_flip_result(item, days=30)

    # Fetch order book from GW2 API
    order_book = asyncio.run(gw2.fetch_order_book(item.id))

    if gw2._client is not None:
        gw2._client = None
    if datawars._client is not None:
        datawars._client = None

    # Print all the information
    print(f"\n{'=' * 60}")
    print(f"{item.name} (ID: {item.id})")
    print(f"{'=' * 60}")

    # Current Prices
    print("\nCurrent Prices:")
    print(
        f"  Buy:  {format_gold(item.buy_price or 0)}  (qty: {item.buy_quantity or 0:,})"
    )
    print(
        f"  Sell: {format_gold(item.sell_price or 0)}  (qty: {item.sell_quantity or 0:,})"
    )
    print(f"  Spread: {format_gold((item.sell_price or 0) - (item.buy_price or 0))}")

    # Vendor Value
    vendor_val = item.vendor_value if item.vendor_value else 0
    print(f"  Vendor Value: {format_gold(vendor_val)}")

    # Order Book
    if order_book and order_book.buys and order_book.sells:
        print("\nOrder Book (top 5 each side):")
        print("  Buys:")
        for listing in order_book.buys[:5]:
            print(f"    {listing['quantity']:,} @ {format_gold(listing['unit_price'])}")
        print("  Sells:")
        for listing in order_book.sells[:5]:
            print(f"    {listing['quantity']:,} @ {format_gold(listing['unit_price'])}")

    # Flip Analysis
    print("\nFlip Analysis:")
    if flip_result:
        print(
            f"  1-day:  profit={flip_result.percent_profit:.2f}%, "
            f"score={format_gold(int(flip_result.flip_score))}/d"
        )
    else:
        print("  1-day:  N/A")
    if flip_result_7d:
        print(
            f"  7-day:  profit={flip_result_7d.percent_profit:.2f}%, "
            f"score={format_gold(int(flip_result_7d.flip_score))}/d"
        )
    else:
        print("  7-day:  N/A")
    if flip_result_30d:
        print(
            f"  30-day: profit={flip_result_30d.percent_profit:.2f}%, "
            f"score={format_gold(int(flip_result_30d.flip_score))}/d"
        )
    else:
        print("  30-day: N/A")

    # Velocity / Volume
    print("\nVelocity (gold/day):")
    print("  Buy orders:")
    print(f"    1-day:  {format_velocity(item.buy_velocity_1d or 0)}")
    print(f"    7-day:  {format_velocity(item.buy_velocity_7d or 0)}")
    print(f"    30-day: {format_velocity(item.buy_velocity_30d or 0)}")
    print("  Sell orders:")
    print(f"    1-day:  {format_velocity(item.sell_velocity_1d or 0)}")
    print(f"    7-day:  {format_velocity(item.sell_velocity_7d or 0)}")
    print(f"    30-day: {format_velocity(item.sell_velocity_30d or 0)}")

    print("\nVolume (items/day):")
    print("  Bought:")
    print(f"    1-day:  {item.buy_sold_1d or 0:,}")
    print(f"    7-day:  {item.buy_sold_7d or 0:,}")
    print(f"    30-day: {item.buy_sold_30d or 0:,}")
    print("  Sold:")
    print(f"    1-day:  {item.sell_sold_1d or 0:,}")
    print(f"    7-day:  {item.sell_sold_7d or 0:,}")
    print(f"    30-day: {item.sell_sold_30d or 0:,}")

    # Competition metrics
    print("\nCompetition:")
    if item.competition_gold is not None:
        print(
            f"  Order book pressure: "
            f"{format_gold_short(int(item.competition_gold))}g in "
            f"{item.competition_tiers or 0} tiers"
        )
    if item.listed_ratio is not None:
        print(f"  Listed/Sold ratio: {item.listed_ratio:.2f}")
    if item.delisted_ratio is not None:
        print(f"  Delisted ratio: {item.delisted_ratio:.2%}")
    if item.spread_percent is not None:
        print(f"  Spread: {item.spread_percent:.2f}%")

    print()
    return 0


async def _run_watch_loop(
    db: Database,
    dw2: DataWars2Client,
    gw2: GW2Client,
    interval: int,
    deep_refresh_seconds: int,
    history_workers: int,
    orderbook_workers: int,
    fetch_order_books: bool,
    limit: int,
    min_profit: float,
    max_profit: Optional[float],
    max_price: int,
    min_sold: int,
    min_bought: int,
) -> None:
    last_deep_refresh_at: Optional[float] = None

    while True:
        try:
            now = time.time()
            deep_refresh_due = (
                last_deep_refresh_at is None
                or (now - last_deep_refresh_at) >= deep_refresh_seconds
            )
            await _run_update_cycle(
                db=db,
                dw2=dw2,
                gw2=gw2,
                full=False,
                deep_refresh=deep_refresh_due,
                history_workers=history_workers,
                orderbook_workers=orderbook_workers,
                fetch_order_books=fetch_order_books,
            )
            if deep_refresh_due:
                last_deep_refresh_at = now

            flips_args = argparse.Namespace(
                days=1,
                limit=limit,
                min_profit=min_profit,
                max_profit=max_profit,
                max_price=max_price,
                min_sold=min_sold,
                min_bought=min_bought,
            )
            cmd_flips(flips_args)

            print(f"\nNext update in {interval} seconds...")
            await asyncio.sleep(interval)
        except KeyboardInterrupt:
            raise


def cmd_watch(args: argparse.Namespace) -> int:
    global VERBOSE, SILENT
    VERBOSE = False
    SILENT = True

    interval = args.interval
    deep_refresh_seconds = args.deep_refresh_seconds

    print(f"Starting watch mode (updating every {interval} seconds)...")
    print(
        f"Deep refresh (history/order books) runs every {deep_refresh_seconds} seconds."
    )
    print("Press Ctrl+C to stop.")
    print()

    db = Database()
    dw2 = DataWars2Client()
    gw2 = GW2Client()

    try:
        asyncio.run(
            _run_watch_loop(
                db=db,
                dw2=dw2,
                gw2=gw2,
                interval=interval,
                deep_refresh_seconds=deep_refresh_seconds,
                history_workers=args.history_workers,
                orderbook_workers=args.orderbook_workers,
                fetch_order_books=args.fetch_order_books,
                limit=args.limit,
                min_profit=args.min_profit,
                max_profit=args.max_profit,
                max_price=args.max_price,
                min_sold=args.min_sold,
                min_bought=args.min_bought,
            )
        )
    except KeyboardInterrupt:
        print("\nWatch mode stopped.")
    finally:
        if dw2._client is not None:
            dw2._client = None
        if gw2._client is not None:
            gw2._client = None

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GW2 Trading Bot - Find profitable flips on the Trading Post"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    update_parser = subparsers.add_parser("update", help="Fetch latest data from APIs")
    update_parser.add_argument(
        "--full",
        action="store_true",
        help=(
            "Fetch full history for ALL items (slow, ~30k items). Without this, "
            "only top 500 items are fetched for faster updates"
        ),
    )
    update_parser.add_argument(
        "--silent",
        action="store_true",
        help="Suppress all output except errors",
    )
    update_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed progress information",
    )
    update_parser.add_argument(
        "--history-workers",
        type=int,
        default=32,
        help="Number of parallel workers for DataWars2 history fetches (default: 32)",
    )
    update_parser.add_argument(
        "--orderbook-workers",
        type=int,
        default=32,
        help="Number of parallel workers for GW2 order book fetches (default: 32)",
    )
    update_parser.add_argument(
        "--fetch-order-books",
        action="store_true",
        help="Fetch order books (slow, ~2s). Without this, only prices/velocity are updated",
    )

    flips_parser = subparsers.add_parser("flips", help="Show best flip opportunities")
    flips_parser.add_argument(
        "--days",
        type=int,
        default=1,
        choices=[1, 7, 30],
        help="Timeframe for velocity calculation (default: 1). 1=24h, 7=7-day avg, 30=30-day avg",
    )
    flips_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of results to show (default: 20)",
    )
    flips_parser.add_argument(
        "--min-profit",
        type=float,
        default=0.0,
        help="Minimum profit percentage filter (default: 0). "
        "E.g., 5 = only show flips with 5+%% profit",
    )
    flips_parser.add_argument(
        "--max-profit",
        type=float,
        default=None,
        help="Maximum profit percentage filter. "
        "E.g., 20 = only show flips with less than 20%% profit",
    )
    flips_parser.add_argument(
        "--max-price",
        type=int,
        default=3000000,
        help="Maximum sell price in copper (default: 3000000 = 300 gold)",
    )
    flips_parser.add_argument(
        "--min-sold",
        type=int,
        default=24,
        help="Minimum average daily sells (default: 1). "
        "E.g., 5 = only show items that sell 5+ per day on average (over 7 days)",
    )
    flips_parser.add_argument(
        "--min-bought",
        type=int,
        default=24,
        help="Minimum average daily buys (default: 1). "
        "E.g., 5 = only show items that have 5+ buy orders per day on average (over 7 days)",
    )

    info_parser = subparsers.add_parser(
        "item",
        help="Show detailed info for an item (search by ID or name)",
    )
    info_parser.add_argument("query", help="Item ID or name to search for")
    info_parser.add_argument(
        "--history",
        action="store_true",
        help="Fetch fresh history data from API (slower)",
    )

    watch_parser = subparsers.add_parser(
        "watch", help="Continuously monitor and update"
    )
    watch_parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Update interval in seconds (default: 300, i.e. 5 minutes)",
    )
    watch_parser.add_argument(
        "--deep-refresh-seconds",
        type=int,
        default=600,
        help="How often to refresh history/order books in watch mode (default: 600)",
    )
    watch_parser.add_argument(
        "--history-workers",
        type=int,
        default=32,
        help="Number of parallel workers for DataWars2 history fetches (default: 32)",
    )
    watch_parser.add_argument(
        "--orderbook-workers",
        type=int,
        default=32,
        help="Number of parallel workers for GW2 order book fetches (default: 32)",
    )
    watch_parser.add_argument(
        "--fetch-order-books",
        action="store_true",
        help="Fetch order books during deep refresh (slow, ~2s)",
    )
    watch_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of flips to show (default: 10)",
    )
    watch_parser.add_argument(
        "--min-profit",
        type=float,
        default=0.0,
        help="Minimum profit percentage filter (default: 0). "
        "E.g., 5 = only show flips with 5+%% profit",
    )
    watch_parser.add_argument(
        "--max-profit",
        type=float,
        default=None,
        help="Maximum profit percentage filter. "
        "E.g., 20 = only show flips with less than 20%% profit",
    )
    watch_parser.add_argument(
        "--max-price",
        type=int,
        default=3000000,
        help="Maximum sell price in copper (default: 3000000 = 300 gold)",
    )
    watch_parser.add_argument(
        "--min-sold",
        type=int,
        default=24,
        help="Minimum average daily sells (default: 1). "
        "E.g., 5 = only show items that sell 5+ per day on average (over 7 days)",
    )
    watch_parser.add_argument(
        "--min-bought",
        type=int,
        default=24,
        help="Minimum average daily buys (default: 1). "
        "E.g., 5 = only show items that have 5+ buy orders per day on average (over 7 days)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "update":
        return cmd_update(args)
    elif args.command == "flips":
        return cmd_flips(args)
    elif args.command == "item":
        return cmd_item(args)
    elif args.command == "watch":
        return cmd_watch(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
