"""Fetch orderbook prices from Polymarket CLOB (no auth required)."""

import requests

CLOB_URL = "https://clob.polymarket.com"


def get_order_book(token_id: str) -> dict:
    """Fetch orderbook for a token. Returns bids/asks."""
    resp = requests.get(
        f"{CLOB_URL}/book",
        params={"token_id": token_id},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()


def mid_from_book(book: dict) -> float | None:
    """Compute mid price from orderbook. Returns None if empty."""
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    if not bids or not asks:
        return None
    best_bid = max(float(b.get("price", 0)) for b in bids)
    best_ask = min(float(a.get("price", 1)) for a in asks)
    if best_bid >= best_ask:
        return (best_bid + best_ask) / 2
    return (best_bid + best_ask) / 2


def get_mid_price(token_id: str) -> float | None:
    """Get mid price for a token."""
    book = get_order_book(token_id)
    return mid_from_book(book)
