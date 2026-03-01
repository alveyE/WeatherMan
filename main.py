#!/usr/bin/env python3
"""
WeatherMan - Weather Market Arbitrage

Runs Agent-01 (scanner) + Agent-02 (fair value) + optionally Agent-03 (executor).
Use --live to execute real trades (requires PRIVATE_KEY, FUNDER_ADDRESS).
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent_01_scanner.scanner import scan
from agent_02_fair_value.edge import find_signals
from shared.ledger import Ledger
from shared.models import Signal


def run_cycle(
    edge_threshold_pct: float = 10.0,
    live: bool = False,
    max_exposure: float = 10.0,
    max_per_trade: float = 2.0,
    ledger: Ledger | None = None,
) -> list[Signal]:
    """Run one scan + fair value cycle. Optionally execute in live mode."""
    print(f"[{datetime.utcnow().isoformat()}Z] Scanning markets...")
    markets = scan()
    print(f"  Found {len(markets)} weather markets")

    mappable = sum(1 for m in markets if m.coords and m.weather_type)
    print(f"  Mappable to NOAA: {mappable}")

    signals = find_signals(markets, edge_threshold_pct=edge_threshold_pct)

    if live and signals and ledger:
        from agent_03_executor.executor import execute_signal

        print(f"\n  LIVE MODE | Max exposure: ${max_exposure} | Per trade: ${max_per_trade}")
        print(f"  Current exposure: ${ledger.total_exposure():.2f} ({ledger.trade_count()} trades)")

        executed = 0
        for s in signals:
            if execute_signal(s, max_exposure, max_per_trade, ledger):
                executed += 1
                print(f"    EXECUTED {s.side}: {s.question[:50]}... @ {s.market_price:.2f}")
        if executed:
            print(f"  Placed {executed} order(s)")
        elif signals:
            print("  No orders placed (limits or already traded)")

    return signals


def main():
    import argparse

    parser = argparse.ArgumentParser(description="WeatherMan weather market arbitrage")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=600, help="Seconds between scans")
    parser.add_argument("--edge", type=float, default=10.0, help="Min edge %% to signal")
    parser.add_argument("--log", type=str, default="signals.jsonl", help="Log file for signals")
    parser.add_argument("--live", action="store_true", help="Execute real trades (requires .env)")
    parser.add_argument("--balance", type=float, default=10.0, help="Max exposure cap in USD (live mode)")
    parser.add_argument("--max-per-trade", type=float, default=2.0, help="Max USD per trade (live mode)")
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
    ledger = Ledger() if args.live else None

    if args.live:
        ledger.set_initial_balance(args.balance)
        if not os.environ.get("PRIVATE_KEY") or not os.environ.get("FUNDER_ADDRESS"):
            print("ERROR: Live mode requires PRIVATE_KEY and FUNDER_ADDRESS in .env")
            sys.exit(1)

    def do_run():
        signals = run_cycle(
            edge_threshold_pct=args.edge,
            live=args.live,
            max_exposure=args.balance,
            max_per_trade=args.max_per_trade,
            ledger=ledger,
        )
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

    if args.once:
        do_run()
        return

    try:
        import time

        while True:
            do_run()
            print(f"\n  Next scan in {args.interval}s...")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
