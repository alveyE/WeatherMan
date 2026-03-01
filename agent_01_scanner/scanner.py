"""Agent-01: Scan weather markets and fetch prices."""

import time
from typing import Iterator

from shared.models import ScannedMarket

from .clob import get_order_book, mid_from_book
from .gamma import extract_markets_from_events, fetch_weather_events
from .parser import parse_question


def scan() -> list[ScannedMarket]:
    """
    Scan all weather markets, fetch orderbook prices, parse questions.
    Returns list of ScannedMarket (no auth required).
    """
    events = fetch_weather_events(limit=80)
    markets = extract_markets_from_events(events)
    results = []

    for m in markets:
        # Fetch orderbook for YES token
        try:
            book_yes = get_order_book(m["yes_token_id"])
            book_no = get_order_book(m["no_token_id"])
        except Exception:
            continue

        yes_mid = mid_from_book(book_yes)
        no_mid = mid_from_book(book_no)
        if yes_mid is None:
            yes_mid = 0.5  # fallback
        if no_mid is None:
            no_mid = 0.5

        parsed = parse_question(m["question"])

        results.append(
            ScannedMarket(
                condition_id=m["condition_id"],
                question=m["question"],
                yes_token_id=m["yes_token_id"],
                no_token_id=m["no_token_id"],
                yes_mid=yes_mid,
                no_mid=no_mid,
                volume_24hr=m["volume_24hr"],
                liquidity=m["liquidity"],
                end_date_iso=m.get("end_date_iso"),
                event_title=m["event_title"],
                location=parsed.get("location"),
                weather_type=parsed.get("weather_type"),
                target_date=parsed.get("target_date"),
                coords=parsed.get("coords"),
            )
        )
        time.sleep(0.05)  # Rate limit

    return results
