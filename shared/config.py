"""Centralized config loaded from config.json (re-read every cycle)."""

import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

DEFAULTS = {
    "entry_threshold": 0.15,
    "exit_threshold": 0.45,
    "min_price": 0.04,
    "max_per_trade_usd": 2.00,
    "max_trades_per_run": 5,
    "scan_interval_seconds": 120,
    "max_exposure_usd": 10.00,
    "edge_min_pct": 10.0,
    "max_slippage": 0.03,  # max cents above scan price for market buys (e.g. 0.03 = 3¢)
}


def load() -> dict:
    """Read config.json and merge with defaults. Safe to call every cycle."""
    cfg = dict(DEFAULTS)
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH) as f:
                cfg.update(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [CONFIG] Failed to read {_CONFIG_PATH}, using defaults: {e}")
    return cfg
