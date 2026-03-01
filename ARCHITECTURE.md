# WeatherMan: Weather Market Arbitrage System

## The Edge (Why This Works)

| Source | Update Frequency | Who Knows First |
|--------|------------------|-----------------|
| **NOAA/NWS** | Every 6 hours (forecast cycles) | Meteorologists |
| **Polymarket** | Every few hours (crowd-driven) | Retail traders |

**Window**: When NOAA updates with new confidence (e.g., Texas rain drops 72% → 63%), Polymarket hasn't repriced yet. You buy YES at 18¢ when fair value suggests it should be higher—or vice versa.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Mac Mini (Closet)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                   │
│  │  Agent-01   │────▶│  Agent-02   │────▶│  Agent-03   │                   │
│  │  Scanner    │     │  Fair Value │     │  Executor   │                   │
│  │  (10 min)   │     │  Builder    │     │  (EIP-712)  │                   │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘                   │
│         │                   │                   │                          │
│         ▼                   ▼                   ▼                          │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                   │
│  │ Polymarket  │     │ NOAA/NWS    │     │ CLOB API    │                   │
│  │ Gamma API   │     │ api.weather │     │ Polygon     │                   │
│  │ 62 markets  │     │ .gov        │     │ chain_id=137│                   │
│  └─────────────┘     └─────────────┘     └─────────────┘                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Agent-01: Market Scanner

**Job**: Poll Polymarket every 10 minutes for all active weather markets and their current prices.

### Data Sources

1. **Gamma API** (market discovery, no auth):
   - `GET https://gamma-api.polymarket.com/events?active=true&closed=false&tag_id=<WEATHER_TAG>&limit=100`
   - Find weather tag ID via `GET https://gamma-api.polymarket.com/tags` (search for "weather" or "climate")
   - Returns events with nested markets; each market has `condition_id`, `clob_token_ids`, `outcomes`, `volume`, `liquidity`

2. **CLOB API** (live orderbook prices):
   - `GET https://clob.polymarket.com/book` — pass `token_id` for each outcome
   - Or use `get_order_book()` from `py-clob-client` (public, no auth)
   - Mid price = (best_bid + best_ask) / 2, or use `calculate_market_price()` for size-adjusted estimates

### Output Schema (per market)

```json
{
  "condition_id": "0x...",
  "question": "Will it rain in Austin, TX on March 5?",
  "yes_token_id": "0x...",
  "no_token_id": "0x...",
  "yes_mid": 0.72,
  "no_mid": 0.28,
  "volume_24hr": 1500,
  "liquidity": 5000,
  "end_date_iso": "2025-03-06T00:00:00Z",
  "location": "Austin, TX",
  "weather_type": "rain",
  "target_date": "2025-03-05"
}
```

### Parsing Challenge

Polymarket weather questions are freeform. You need to:
- **Extract location**: "Austin, TX", "Texas", "Houston" → geocode to lat/lon
- **Extract weather type**: rain, snow, temp > 90°F, etc.
- **Extract target date**: "March 5", "this weekend"
- **Map to NOAA**: Same location + date → fetch NWS forecast

Use regex + simple NLP, or a small LLM call for structured extraction. Store a `market_id → (lat, lon, weather_type, date)` mapping.

### Implementation

- **Language**: Python (matches `py-clob-client`)
- **Schedule**: `cron` every 10 min, or `schedule`/`apscheduler` in a long-running process
- **Storage**: Write to SQLite/JSON/Redis; Agent-02 reads from here

---

## Agent-02: Fair Value Builder

**Job**: For each market from Agent-01, compute fair value from NOAA + optional signals.

### NOAA/NWS API (Free, No Key)

**Base URL**: `https://api.weather.gov`  
**Required Header**: `User-Agent: (WeatherMan/1.0, your@email.com)` — NWS requires this.

**Flow**:

1. **Geocode** location → lat, lon (use `geopy` or a free API)
2. **Get gridpoint**:
   ```
   GET https://api.weather.gov/points/{lat},{lon}
   ```
   Response has `properties.forecast` and `properties.forecastHourly` URLs.

3. **Get forecast**:
   ```
   GET {forecast_url}
   ```
   Returns `properties.periods[]` — each period has:
   - `name`, `startTime`, `endTime`
   - `temperature`, `temperatureUnit`
   - `probabilityOfPrecipitation` (PoP) — **this is your rain confidence**
   - `shortForecast`, `detailedForecast`

4. **Map to market**:
   - Match market target date to forecast period(s)
   - For "Will it rain?": fair value YES ≈ `probabilityOfPrecipitation / 100`
   - For temp markets: parse "High 92" → binary outcome based on threshold

### Confidence / Model Uncertainty

The NWS forecast is a single number. For "confidence" you can:
- Use **ensemble spread** if you pull from NDFD/GEFS (more complex)
- Use **forecast age**: older forecast = lower confidence, discount the edge
- Use **PoP gradient**: if PoP jumps 72→63 between cycles, that's a strong signal

### Optional Signals (Agent-02+)

- **On-chain**: Volume, order flow imbalance
- **Sentiment**: Twitter/Reddit (optional, adds latency)
- **Historical accuracy**: Track which locations/types you're best at

### Output

```json
{
  "condition_id": "0x...",
  "fair_value_yes": 0.63,
  "market_yes": 0.72,
  "edge_pct": 0.14,
  "signal": "SHORT_YES",
  "confidence": 0.85
}
```

**Edge threshold**: Only flag when `|fair_value - market_price| > X%` (e.g. 10–14%).

---

## Agent-03: Executor

**Job**: When Agent-02 flags a mispricing, sign and post orders to the CLOB.

### Setup

1. **Wallet**: EOA or Polymarket proxy (Gnosis Safe)
   - If Polymarket.com account: export key from Settings → use `signature_type=2`, `funder=proxy_address`
   - If standalone: `signature_type=0`, funder = your EOA

2. **Polygon**: Need POL for gas (if EOA). Polymarket uses chain_id 137.

3. **API credentials** (one-time):
   ```python
   from py_clob_client.client import ClobClient
   client = ClobClient(
       "https://clob.polymarket.com",
       key=os.environ["PRIVATE_KEY"],
       chain_id=137,
       signature_type=2,  # or 0 for EOA
       funder="0x..."    # proxy or EOA
   )
   api_creds = client.create_or_derive_api_creds()
   client.set_api_creds(api_creds)
   ```

### Order Flow

1. **Receive signal** from Agent-02: `{ condition_id, token_id, side, price, size }`
2. **Size**: Start small (e.g. $10–25 per trade). Scale with edge confidence.
3. **Place order**:
   ```python
   from py_clob_client.clob_types import OrderArgs, OrderType
   from py_clob_client.order_builder.constants import BUY, SELL
   
   response = client.create_and_post_order(
       OrderArgs(
           token_id=token_id,
           price=0.18,   # e.g. buy YES at 18¢
           size=100.0,   # units
           side=BUY
       ),
       order_type=OrderType.GTC
   )
   ```
4. **EIP-712**: The SDK signs the order internally. No manual signing needed.

### Risk Controls

- **Max position**: Cap total exposure per market
- **Max drawdown**: Pause if daily/weekly drawdown exceeds threshold
- **Cooldown**: Don't re-enter same market within N hours
- **Slippage**: Use limit orders; avoid market orders on thin books

---

## Data Flow Summary

```
Agent-01 (every 10 min):
  Gamma API → events (weather tag) → markets
  CLOB API  → orderbook per token → mid prices
  → Write to shared store (market_id, yes_mid, no_mid, metadata)

Agent-02 (on new data or every 10 min):
  Read shared store
  For each market: geocode → NWS points → forecast

  Match forecast period to market target date
  fair_value_yes = probabilityOfPrecipitation / 100  (for rain)
  edge = |fair_value - market_yes|
  If edge > threshold → emit signal

Agent-03 (on signal):
  Receive signal
  Check risk limits
  create_and_post_order(...)
  Log trade
```

---

## Tech Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.11+ |
| Polymarket | `py-clob-client` |
| NOAA | `requests` + `api.weather.gov` |
| Geocoding | `geopy` (Nominatim) or Google Geocoding API |
| Scheduling | `apscheduler` or `cron` |
| Storage | SQLite |
| Secrets | `.env` (never commit) |

---

## Project Structure

```
WeatherMan/
├── agent_01_scanner/
│   ├── __init__.py
│   ├── gamma.py
│   ├── clob.py
│   └── parser.py
├── agent_02_fair_value/
│   ├── __init__.py
│   ├── noaa.py
│   ├── geocode.py
│   └── edge.py
├── agent_03_executor/
│   ├── __init__.py
│   ├── client.py
│   └── risk.py
├── shared/
│   ├── models.py
│   └── store.py
├── main.py
├── requirements.txt
└── .env.example
```

---

## Getting Started

1. **Discover weather tag**: `curl "https://gamma-api.polymarket.com/tags" | jq '.[] | select(.label | test("weather"; "i"))'`
2. **Test NWS**: `curl -H "User-Agent: (WeatherMan, you@email.com)" "https://api.weather.gov/points/30.27,-97.74"`
3. **Paper trade first**: Run Agent-01 + Agent-02, log signals without executing. Backtest on historical data if available.
4. **Start small**: $10–25 per trade, 5–10 trades before scaling.

---

## Key Metrics to Track

- **Win rate** (target: 65%+)
- **Avg per trade** (target: $15–25)
- **Max drawdown** (target: <5%)
- **Edge distribution**: % of signals by edge size
- **Latency**: Time from NOAA update to order fill

---

## References

- [Polymarket CLOB](https://docs.polymarket.com/developers/CLOB/introduction)
- [Polymarket Gamma API](https://docs.polymarket.com/market-data/fetching-markets)
- [NWS API](https://www.weather.gov/documentation/services-web-api)
- [py-clob-client](https://github.com/Polymarket/py-clob-client)
