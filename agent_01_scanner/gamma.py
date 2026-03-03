"""Fetch weather markets from Polymarket Gamma API."""

import json
from functools import lru_cache

import requests

GAMMA_URL = "https://gamma-api.polymarket.com"
WEATHER_TAG_ID = "84"  # Polymarket "Weather" tag


def check_market_resolution(token_id: str) -> dict | None:
    """
    Query Gamma for a specific market's resolution status using its CLOB token ID.
    Returns {"closed": bool, "yes_price": float, "no_price": float} or None on failure.

    For resolved markets, outcomePrices snaps to ["0","1"] or ["1","0"].
    """
    try:
        resp = requests.get(
            f"{GAMMA_URL}/markets",
            params={"clob_token_ids": token_id},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            market = data[0] if data else None
        else:
            market = data
        if not market:
            return None

        closed = bool(market.get("closed", False))
        raw_prices = market.get("outcomePrices")
        if isinstance(raw_prices, str):
            raw_prices = json.loads(raw_prices)
        if not raw_prices or len(raw_prices) < 2:
            return {"closed": closed, "yes_price": None, "no_price": None}

        return {
            "closed": closed,
            "yes_price": float(raw_prices[0]),
            "no_price": float(raw_prices[1]),
        }
    except Exception:
        return None


def fetch_weather_events(limit: int = 100) -> list[dict]:
    """Fetch active weather events from Gamma API."""
    resp = requests.get(
        f"{GAMMA_URL}/events",
        params={
            "tag_id": WEATHER_TAG_ID,
            "active": "true",
            "closed": "false",
            "limit": limit,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def extract_markets_from_events(events: list[dict]) -> list[dict]:
    """Flatten events into individual markets with metadata."""
    markets = []
    for event in events:
        event_title = event.get("title", "")
        event_id = str(event.get("id") or event.get("slug") or event_title)
        for market in event.get("markets", []):
            condition_id = market.get("conditionId") or market.get("condition_id")
            raw_clob = market.get("clobTokenIds") or market.get("clob_token_ids") or "[]"
            if isinstance(raw_clob, str):
                try:
                    clob_ids = json.loads(raw_clob)
                except json.JSONDecodeError:
                    clob_ids = []
            else:
                clob_ids = raw_clob or []
            if not condition_id or len(clob_ids) < 2:
                continue
            markets.append({
                "condition_id": condition_id,
                "question": market.get("question", ""),
                "yes_token_id": str(clob_ids[0]),
                "no_token_id": str(clob_ids[1]),
                "event_title": event_title,
                "event_id": event_id,
                "volume_24hr": float(market.get("volume24hr") or market.get("volume_24hr") or 0),
                "liquidity": float(market.get("liquidity") or 0),
                "end_date_iso": market.get("endDateIso") or market.get("endDate") or market.get("end_date"),
            })
    return markets
