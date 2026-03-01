#!/usr/bin/env python3
"""
WeatherMan Paper Trading - Proof of Concept

Runs Agent-01 (scanner) + Agent-02 (fair value) in a loop.
Logs signals to stdout and signals.jsonl - NO real execution.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agent_01_scanner.scanner import scan
from agent_02_fair_value.edge import find_signals
from shared.models import Signal


def run_cycle(edge_threshold_pct: float = 10.0) -> list[Signal]:
    """Run one scan + fair value cycle. Returns signals (paper mode)."""
    print(f"[{datetime.utcnow().isoformat()}Z] Scanning markets...")
    markets = scan()
    print(f"  Found {len(markets)} weather markets")

    mappable = sum(1 for m in markets if m.coords and m.weather_type)
    print(f"  Mappable to NOAA: {mappable}")

    signals = find_signals(markets, edge_threshold_pct=edge_threshold_pct)
    return signals


def main():
    import argparse
    parser = argparse.ArgumentParser(description="WeatherMan paper trading")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=600, help="Seconds between scans (default: 600)")
    parser.add_argument("--edge", type=float, default=10.0, help="Min edge %% to signal (default: 10)")
    parser.add_argument("--log", type=str, default="signals.jsonl", help="Log file for signals")
    args = parser.parse_args()

    log_path = Path(args.log)

    def do_run():
        signals = run_cycle(edge_threshold_pct=args.edge)
        if signals:
            print(f"\n  *** {len(signals)} SIGNAL(S) ***")
            for s in signals:
                print(f"    {s.side}: {s.question[:60]}...")
                print(f"      Market: {s.market_price:.2f} | Fair: {s.fair_value:.2f} | Edge: {s.edge_pct:.1f}%")
                # Append to log
                with open(log_path, "a") as f:
                    f.write(json.dumps({
                        "timestamp": s.timestamp.isoformat(),
                        "condition_id": s.condition_id,
                        "question": s.question,
                        "side": s.side,
                        "token_id": s.token_id,
                        "market_price": s.market_price,
                        "fair_value": s.fair_value,
                        "edge_pct": s.edge_pct,
                    }) + "\n")
        else:
            print("  No signals above threshold")

    if args.once:
        do_run()
        return

    # Loop with interval
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
