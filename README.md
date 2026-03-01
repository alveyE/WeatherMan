# WeatherMan — Paper Trading PoC

Weather market arbitrage: exploit the lag between NOAA forecast updates (every 6 hours) and Polymarket repricing.

**This is a proof-of-concept.** No real money. No private keys. No execution.

## Quick Start

```bash
pip install requests
python main.py --once --edge 10
```

- `--once`: Run one scan and exit
- `--edge 10`: Only signal when edge > 10% (default)
- `--interval 600`: When looping, scan every 10 minutes
- `--log signals.jsonl`: Append signals to this file

## What It Does

1. **Agent-01 (Scanner)**: Fetches ~100 weather markets from Polymarket, gets orderbook mid prices
2. **Agent-02 (Fair Value)**: For precipitation markets (NYC, Seattle, etc.), fetches NOAA forecast and computes fair value from probability-of-precipitation
3. **Signals**: When `|fair_value - market_price| > edge_threshold`, logs a signal

No Agent-03 (execution) — paper mode only.

## Output

```
[2026-03-01T06:30:00Z] Scanning markets...
  Found 98 weather markets
  Mappable to NOAA: 17
  *** 3 SIGNAL(S) ***
    BUY_NO: Will NYC have between 3 and 4 inches...
      Market: 0.15 | Fair: 0.08 | Edge: 12.3%
```

Signals are also appended to `signals.jsonl`.

## Limitations (PoC)

- **Fair value**: For "Will NYC have between 3–4 inches in February?", we use average daily PoP as a rough proxy. Real fair value would need historical distribution + forecast.
- **Markets**: Only precipitation markets with known cities (NYC, Seattle, Austin, etc.) are mapped.
- **No execution**: Add Agent-03 and `py-clob-client` when ready for live trading.

## Next Steps

1. Run for 24–48 hours, collect signals
2. Manually track: would these have been profitable?
3. Tune `--edge` threshold
4. Add more cities to `agent_01_scanner/parser.py`
5. When confident: add Agent-03 with real execution (small size first)
