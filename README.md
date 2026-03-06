# WeatherMan — Weather Market Arbitrage

Exploit the lag between NOAA forecast updates (every 6 hours) and Polymarket repricing.

## Quick Start (Paper Mode)

```bash
pip install -r requirements.txt
python main.py --once --edge 10
```

### Linux / server (externally-managed Python)

On Debian/Ubuntu and similar, use a virtual environment so you can install packages without `--break-system-packages`:

```bash
python3 -m venv .venv
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py --once
```

For live trading, after activating the venv run `python main.py --live`.

## Live Trading

```bash
# 1. Copy env template
cp .env.example .env

# 2. Add your Polymarket credentials to .env
#    - PRIVATE_KEY: Export from polymarket.com/settings
#    - FUNDER_ADDRESS: Your proxy wallet address (shown in Polymarket profile)

# 3. Deposit USDC to your Polymarket account

# 4. Run with --live and balance cap
python main.py --live --balance 10 --max-per-trade 2 --once
```

### Live Mode Options

| Flag | Default | Description |
|------|---------|-------------|
| `--live` | off | Execute real trades |
| `--balance` | 10 | Max total exposure in USD (cap) |
| `--max-per-trade` | 2 | Max USD per single trade |

The bot tracks exposure in `ledger.json` and will not place new trades once total exposure reaches your cap.

## What It Does

1. **Agent-01**: Scans Polymarket weather markets, fetches orderbook prices
2. **Agent-02**: Computes fair value from NOAA forecast (PoP for precipitation)
3. **Agent-03** (live only): Places limit orders when edge > threshold, respects balance cap

## Output

```
[2026-03-01T06:30:00Z] Scanning markets...
  Found 98 weather markets
  Mappable to NOAA: 17

  LIVE MODE | Max exposure: $10 | Per trade: $2
  Current exposure: $0.00 (0 trades)
  *** 2 SIGNAL(S) ***
    EXECUTED BUY_NO: Will NYC have between 3 and 4 inches...
    [LIVE] BUY_NO: Will Seattle have less than 3 inches...
      Market: 0.15 | Fair: 0.08 | Edge: 12.3%
```

## Security

- Never commit `.env` or `ledger.json`
- Start with small balance ($10–25)
- Polymarket is non-custodial — you control the wallet
