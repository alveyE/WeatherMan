#!/usr/bin/env python3
"""
WeatherMan - Weather Market Arbitrage

All tunable settings live in config.json (hot-reloaded every cycle).
Paper mode (default) simulates trades with real market data and tracks P&L.
Use --live to execute real trades (requires PRIVATE_KEY, FUNDER_ADDRESS in .env).
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent_01_scanner.scanner import scan
from agent_02_fair_value.edge import find_signals
from shared import config as cfg
from shared.ledger import Ledger
from shared.models import Signal


def _print_pnl(ledger: Ledger, mode: str):
    """Print portfolio P&L dashboard."""
    s = ledger.pnl_summary()
    total_trades = s["closed_count"] + s["open_count"]
    win_rate = (s["wins"] / s["closed_count"] * 100) if s["closed_count"] else 0

    print(f"\n  {'=' * 50}")
    print(f"  [{mode}] PORTFOLIO")
    print(f"  {'=' * 50}")
    print(f"  Open positions:   {s['open_count']}  (exposure ${s['open_exposure']:.2f})")
    print(f"  Closed trades:    {s['closed_count']}  ({s['wins']}W / {s['losses']}L — {win_rate:.0f}% win rate)")
    print(f"  Total trades:     {total_trades}")
    print(f"  Realized P&L:     ${s['realized_pnl']:+.2f}")
    print(f"  Unrealized value: ${s['unrealized_value']:.2f}")
    print(f"  {'=' * 50}")


def run_cycle(
    settings: dict,
    live: bool,
    ledger: Ledger,
) -> list[Signal]:
    """Run one full scan + fair value + execution cycle (paper or live)."""
    mode = "LIVE" if live else "PAPER"
    print(f"[{datetime.now(timezone.utc).isoformat()}] Scanning markets... ({mode})")
    markets = scan()
    print(f"  Found {len(markets)} weather markets (within 2-day window)")

    mappable = sum(1 for m in markets if m.coords and m.weather_type)
    print(f"  Mappable to NOAA: {mappable}")

    signals = find_signals(
        markets,
        edge_threshold_pct=settings["edge_min_pct"],
        entry_threshold=settings["entry_threshold"],
        min_price=settings["min_price"],
    )

    max_exposure = settings["max_exposure_usd"]
    max_per_trade = settings["max_per_trade_usd"]
    max_trades = settings["max_trades_per_run"]
    exit_thresh = settings["exit_threshold"]

    print(f"\n  Exposure cap: ${max_exposure} | Per trade: ${max_per_trade} | "
          f"Entry ≤ {settings['entry_threshold']:.0%} | Exit ≥ {exit_thresh:.0%}")
    print(f"  Current exposure: ${ledger.total_exposure():.2f} ({len(ledger.open_positions())} open)")

    # --- Exit scan ---
    if live:
        from agent_03_executor.executor import check_exits, execute_signal
        exited = check_exits(ledger, exit_thresh)
    else:
        from agent_03_executor.paper import paper_check_exits, paper_execute_signal
        exited = paper_check_exits(ledger, exit_thresh)

    if exited:
        print(f"  Closed {exited} position(s) (exit threshold {exit_thresh:.0%})")

    # --- Entry scan (capped at max_trades_per_run) ---
    executed = 0
    for s in signals:
        if executed >= max_trades:
            break
        if live:
            ok = execute_signal(s, max_exposure, max_per_trade, ledger)
        else:
            ok = paper_execute_signal(s, max_exposure, max_per_trade, ledger)
        if ok:
            executed += 1
            print(f"    [{mode} BUY] {s.side}: {s.question[:50]}... @ {s.market_price:.2f}")

    if executed:
        print(f"  Placed {executed} order(s) (limit {max_trades}/run)")
    elif signals:
        print("  No orders placed (limits or already traded)")

    # --- P&L dashboard ---
    _print_pnl(ledger, mode)

    return signals


def main():
    import argparse

    parser = argparse.ArgumentParser(description="WeatherMan weather market arbitrage")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--live", action="store_true", help="Execute real trades (requires .env)")
    parser.add_argument("--log", type=str, default="signals.jsonl", help="Signal log file")
    args = parser.parse_args()

    # Load .env if present
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    log_path = Path(args.log)

    if args.live:
        if not os.environ.get("PRIVATE_KEY") or not os.environ.get("FUNDER_ADDRESS"):
            print("ERROR: Live mode requires PRIVATE_KEY and FUNDER_ADDRESS in .env")
            sys.exit(1)
        ledger = Ledger("ledger.json")
    else:
        ledger = Ledger("paper_ledger.json")

    def do_run():
        settings = cfg.load()
        ledger.set_initial_balance(settings["max_exposure_usd"])

        signals = run_cycle(settings=settings, live=args.live, ledger=ledger)

        if signals:
            print(f"\n  *** {len(signals)} SIGNAL(S) ***")
            for s in signals:
                mode = "LIVE" if args.live else "PAPER"
                print(f"    [{mode}] {s.side}: {s.question[:55]}...")
                print(f"      Market: {s.market_price:.2f} | Fair: {s.fair_value:.2f} | Edge: {s.edge_pct:.1f}%")
                with open(log_path, "a") as f:
                    f.write(
                        json.dumps(
                            {
                                "timestamp": s.timestamp.isoformat(),
                                "condition_id": s.condition_id,
                                "event_id": s.event_id,
                                "question": s.question,
                                "side": s.side,
                                "token_id": s.token_id,
                                "market_price": s.market_price,
                                "fair_value": s.fair_value,
                                "edge_pct": s.edge_pct,
                                "live": args.live,
                            }
                        )
                        + "\n"
                    )
        else:
            print("  No signals above threshold")

        return settings

    if args.once:
        do_run()
        return

    try:
        import time

        while True:
            settings = do_run()
            interval = settings["scan_interval_seconds"]
            print(f"\n  Next scan in {interval}s...")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
