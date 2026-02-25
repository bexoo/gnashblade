import argparse

import gw2_trader


def test_cmd_update_always_uses_deep_refresh(monkeypatch):
    captured = {}

    monkeypatch.setattr(gw2_trader, "Database", lambda: object())
    monkeypatch.setattr(gw2_trader, "DataWars2Client", lambda: object())
    monkeypatch.setattr(gw2_trader, "GW2Client", lambda: object())

    def fake_run_update_cycle(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(gw2_trader, "_run_update_cycle", fake_run_update_cycle)

    args = argparse.Namespace(
        full=False,
        verbose=False,
        silent=True,
        history_workers=16,
        orderbook_workers=24,
    )
    result = gw2_trader.cmd_update(args)

    assert result == 0
    assert captured["deep_refresh"] is True
    assert captured["history_workers"] == 16
    assert captured["orderbook_workers"] == 24


def test_cmd_watch_respects_deep_refresh_seconds(monkeypatch):
    deep_refresh_flags = []
    now = {"value": 0.0}
    sleep_calls = {"count": 0}

    monkeypatch.setattr(gw2_trader, "Database", lambda: object())
    monkeypatch.setattr(gw2_trader, "DataWars2Client", lambda: object())
    monkeypatch.setattr(gw2_trader, "GW2Client", lambda: object())
    monkeypatch.setattr(gw2_trader, "cmd_flips", lambda args: 0)
    monkeypatch.setattr(gw2_trader.time, "time", lambda: now["value"])

    def fake_run_update_cycle(**kwargs):
        deep_refresh_flags.append(kwargs["deep_refresh"])

    monkeypatch.setattr(gw2_trader, "_run_update_cycle", fake_run_update_cycle)

    def fake_sleep(seconds: float):
        now["value"] += seconds
        sleep_calls["count"] += 1
        if sleep_calls["count"] >= 4:
            raise KeyboardInterrupt()

    monkeypatch.setattr(gw2_trader.time, "sleep", fake_sleep)

    args = argparse.Namespace(
        interval=60,
        deep_refresh_seconds=180,
        history_workers=12,
        orderbook_workers=12,
        limit=10,
        min_profit=0.0,
        max_profit=None,
        max_price=3000000,
        min_sold=1,
        min_bought=1,
    )
    result = gw2_trader.cmd_watch(args)

    assert result == 0
    assert deep_refresh_flags == [True, False, False, True]
