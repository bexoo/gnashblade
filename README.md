# Gnashblade

A Python-based Guild Wars 2 trading bot that uses the DataWars2 and GW2 APIs to track item prices, calculate velocity metrics, identify profitable flips, and measure market competition. The project uses SQLite for data storage.

## Architecture

```
gw2_trader.py              # Unified CLI entry point
lib/
├── __init__.py            # Package exports
├── api.py                 # DataWars2Client + GW2Client (order books)
├── calculator.py          # Profit, velocity, competition, flip score
├── database.py            # SQLite operations (gw2.db)
└── models.py              # Dataclasses: Item, FlipResult, HistoryEntry, OrderBook
tests/
├── __init__.py
└── test_calculator.py     # Unit tests for calculator module
```

## CLI Commands

```bash
# Update data (quick: prices + top 500 items with history)
python gw2_trader.py update

# Update data (full: all items with history - slow)
python gw2_trader.py update --full

# Show best flips (default: 1-day velocity, top 20)
python gw2_trader.py flips

# Show flips with custom options
python gw2_trader.py flips --days 7 --limit 50 --min-profit 5

# Show detailed info for a specific item
python gw2_trader.py info <item_id>

# Continuous monitoring mode
python gw2_trader.py watch

# Watch with custom interval (seconds)
python gw2_trader.py watch --interval 60
```

## Metrics

### Flip Score Calculation

The flip score represents the expected daily gold profit from flipping an item:

```
flip_velocity = min(buy_velocity, sell_velocity)  # gold/day
percent_profit = ((sell_price - 1) * 0.85 - (buy_price + 1)) / (buy_price + 1) * 100
flip_score = flip_velocity * (percent_profit / 100)  # gold profit per day
```

- `flip_score` is stored in copper internally, divided by 10000 for display
- Prices displayed in `xg ys zc` format (e.g., "32g00s47c")
- Default max price filter: 300g (3,000,000 copper)

### Competition Metrics

1. **Listed/Sold Ratio**: Orders placed per transaction (higher = more competitive)
2. **Order Book Competition**: Gold value in orders above yesterday's floor price
3. **Price Pressure**: Spread compression + delisted ratio

### Data Sources

| Data | Source | Endpoint |
|------|--------|----------|
| Prices, quantities | DataWars2 | `/gw2/v1/items/csv` |
| Velocity, price stats | DataWars2 | `/gw2/v1/history?itemID=X&days=N` |
| Order book tiers | GW2 Official | `/v2/commerce/listings/{id}` |

Note: DataWars2 `buy_value`/`sell_value` is in copper — divide by 10000 for gold.


## Known Issues
- **Slow updates**: History fetches are sequential (500+ API calls). Could benefit from async/parallel fetching.
- **Order book data sparse**: Many top flip items lack competition data because full update takes a long time and gets interrupted.
- **No caching**: Re-fetches all data even if recent. Could skip items updated within the last N minutes.
- **Outliers**: Some items have flip scores that are suspiciously high (items with 200%+ profit margin should generally not have high flip scores due to low velocity).
