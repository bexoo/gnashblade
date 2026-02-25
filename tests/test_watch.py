import argparse

import gw2_trader


def test_watch_deep_refresh_runs_on_first_loop_and_interval(monkeypatch):
    deep_refresh_flags = []
    now = {"value": 0.0}
    sleep_calls = {"count": 0}

    monkeypatch.setattr(gw2_trader, "Database", lambda: object())
    monkeypatch.setattr(gw2_trader, "DataWars2Client", lambda: object())
    monkeypatch.setattr(gw2_trader, "GW2Client", lambda: object())
    monkeypatch.setattr(gw2_trader, "cmd_flips", lambda args: 0)

    def fake_run_update_cycle(**kwargs):
        deep_refresh_flags.append(kwargs["deep_refresh"])

    monkeypatch.setattr(gw2_trader, "_run_update_cycle", fake_run_update_cycle)
    monkeypatch.setattr(gw2_trader.time, "time", lambda: now["value"])

    def fake_sleep(seconds: float):
        now["value"] += seconds
        sleep_calls["count"] += 1
        if sleep_calls["count"] >= 3:
            raise KeyboardInterrupt()

    monkeypatch.setattr(gw2_trader.time, "sleep", fake_sleep)

    args = argparse.Namespace(
        interval=60,
        deep_refresh_seconds=120,
        history_workers=8,
        orderbook_workers=8,
        limit=10,
        min_profit=0.0,
        max_profit=None,
        max_price=3000000,
        min_sold=1,
        min_bought=1,
    )
    result = gw2_trader.cmd_watch(args)

    assert result == 0
    assert deep_refresh_flags == [True, False, True]
