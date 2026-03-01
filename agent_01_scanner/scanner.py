"""Agent-01: Scan weather markets and fetch prices."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from shared.models import ScannedMarket

from .clob import get_order_book, mid_from_book
from .gamma import extract_markets_from_events, fetch_weather_events
from .parser import parse_question

MAX_DAYS_OUT = 2
ORDERBOOK_WORKERS = 10


def _resolves_within_window(end_date_iso: str | None) -> bool:
    """Return True if the market resolves within MAX_DAYS_OUT days."""
    if not end_date_iso:
        return False
    try:
        end_dt = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) + timedelta(days=MAX_DAYS_OUT)
        return end_dt <= cutoff
    except (ValueError, TypeError):
        return False


def _fetch_books(m: dict) -> tuple[dict, float | None, float | None]:
    """Fetch yes/no orderbooks for a market. Returns (market_dict, yes_mid, no_mid)."""
    try:
        book_yes = get_order_book(m["yes_token_id"])
        book_no = get_order_book(m["no_token_id"])
        return m, mid_from_book(book_yes), mid_from_book(book_no)
    except Exception:
        return m, None, None


def scan() -> list[ScannedMarket]:
    """
    Scan all weather markets, fetch orderbook prices, parse questions.
    Filters: resolves within MAX_DAYS_OUT, has known location + weather type.
    Only fetches orderbooks for markets that pass all cheap filters first.
    Uses a thread pool to fetch orderbooks concurrently.
    """
    events = fetch_weather_events(limit=80)
    markets = extract_markets_from_events(events)

    # Cheap filters first (no HTTP) to avoid hundreds of orderbook requests
    candidates: dict[str, tuple[dict, dict]] = {}
    for m in markets:
        if not _resolves_within_window(m.get("end_date_iso")):
            continue
        parsed = parse_question(m["question"])
        if not parsed.get("coords") or not parsed.get("weather_type"):
            continue
        candidates[m["condition_id"]] = (m, parsed)

    print(f"  Fetching orderbooks for {len(candidates)} candidates...")

    # Fetch orderbooks concurrently
    book_results: dict[str, tuple[float, float]] = {}
    with ThreadPoolExecutor(max_workers=ORDERBOOK_WORKERS) as pool:
        futures = {
            pool.submit(_fetch_books, m): cid
            for cid, (m, _) in candidates.items()
        }
        for future in as_completed(futures):
            m, yes_mid, no_mid = future.result()
            if yes_mid is not None or no_mid is not None:
                book_results[m["condition_id"]] = (
                    yes_mid if yes_mid is not None else 0.5,
                    no_mid if no_mid is not None else 0.5,
                )

    results = []
    for cid, (m, parsed) in candidates.items():
        if cid not in book_results:
            continue
        yes_mid, no_mid = book_results[cid]

        results.append(
            ScannedMarket(
                condition_id=cid,
                question=m["question"],
                yes_token_id=m["yes_token_id"],
                no_token_id=m["no_token_id"],
                yes_mid=yes_mid,
                no_mid=no_mid,
                volume_24hr=m["volume_24hr"],
                liquidity=m["liquidity"],
                end_date_iso=m.get("end_date_iso"),
                event_title=m["event_title"],
                event_id=m.get("event_id"),
                location=parsed.get("location"),
                weather_type=parsed.get("weather_type"),
                target_date=parsed.get("target_date"),
                coords=parsed.get("coords"),
                threshold_low=parsed.get("threshold_low"),
                threshold_high=parsed.get("threshold_high"),
            )
        )

    return results
