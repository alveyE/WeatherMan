"""Paper-trading executor: simulates buys/sells using real market prices."""

from agent_01_scanner.clob import get_mid_price
from agent_01_scanner.gamma import check_market_resolution
from shared.ledger import Ledger
from shared.models import Signal


def paper_execute_signal(
    signal: Signal,
    max_exposure: float,
    max_per_trade_usd: float,
    ledger: Ledger,
) -> bool:
    """Simulate a BUY -- same risk checks as live, but no CLOB order."""
    if ledger.has_traded(signal.condition_id):
        return False
    if signal.event_id and ledger.has_traded_event(signal.event_id):
        return False

    current = ledger.total_exposure()
    price = signal.market_price

    size_usd = min(max_per_trade_usd, max_exposure - current)
    if size_usd < 0.5:
        return False

    size = round(size_usd / price, 2)
    if size < 0.1:
        return False

    cost = price * size
    if current + cost > max_exposure:
        return False

    ledger.record_trade(
        condition_id=signal.condition_id,
        token_id=signal.token_id,
        side=signal.side,
        price=price,
        size=size,
        question=signal.question,
        event_id=signal.event_id,
        end_date_iso=signal.end_date_iso,
    )
    return True


def _resolve_position(pos: dict, ledger: Ledger) -> bool:
    """
    Check if a position's market has resolved on Polymarket.
    If resolved, close the position at $1.00 (win) or $0.00 (loss).
    Returns True if the position was closed.
    """
    token_id = pos["token_id"]
    info = check_market_resolution(token_id)
    if info is None or not info.get("closed"):
        return False

    yes_price = info.get("yes_price")
    no_price = info.get("no_price")
    if yes_price is None or no_price is None:
        return False

    # outcomePrices snaps to [0,1] or [1,0] on resolution;
    # if neither is near 1.0, the market closed without resolving yet
    if max(yes_price, no_price) < 0.95:
        return False

    side = pos.get("side", "")
    if side == "BUY_YES":
        sell_price = yes_price
    elif side == "BUY_NO":
        sell_price = no_price
    else:
        return False

    sell_price = round(sell_price, 2)
    ledger.close_position(pos["condition_id"], sell_price=sell_price)
    profit = round((sell_price - pos["price"]) * pos["size"], 2)
    tag = "WIN" if sell_price > 0.5 else "LOSS"
    print(f"    [PAPER RESOLVED {tag}] {pos['question'][:50]}... → ${sell_price:.2f} (P&L ${profit:+.2f})")
    return True


def paper_check_exits(ledger: Ledger, exit_threshold: float) -> int:
    """
    Check open paper positions against live market prices.
    1. If CLOB mid >= exit_threshold → close (take profit)
    2. If CLOB returns None (market closed) → query Gamma for resolution
    3. Otherwise update mark price for unrealized P&L
    """
    positions = ledger.open_positions()
    if not positions:
        return 0

    closed = 0
    for pos in positions:
        token_id = pos["token_id"]

        mid = None
        try:
            mid = get_mid_price(token_id)
        except Exception:
            pass

        if mid is not None:
            ledger.update_mark(pos["condition_id"], mid)

            if mid >= exit_threshold:
                ledger.close_position(pos["condition_id"], sell_price=round(mid, 2))
                closed += 1
                profit = round((mid - pos["price"]) * pos["size"], 2)
                print(f"    [PAPER EXIT] {pos['question'][:50]}... @ {mid:.2f} (profit ~${profit})")
                continue

        if mid is None:
            if _resolve_position(pos, ledger):
                closed += 1

    return closed
