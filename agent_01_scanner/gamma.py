"""Fetch weather markets from Polymarket Gamma API."""

import json
import requests

GAMMA_URL = "https://gamma-api.polymarket.com"
WEATHER_TAG_ID = "84"  # Polymarket "Weather" tag


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
