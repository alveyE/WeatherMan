"""Paper-trading executor: simulates buys/sells using real market prices."""

from agent_01_scanner.clob import get_mid_price
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
    )
    return True


def paper_check_exits(ledger: Ledger, exit_threshold: float) -> int:
    """
    Check open paper positions against live market prices.
    Close any whose mid price >= exit_threshold.
    Also updates mark prices on positions that stay open.
    """
    positions = ledger.open_positions()
    if not positions:
        return 0

    closed = 0
    for pos in positions:
        token_id = pos["token_id"]
        try:
            mid = get_mid_price(token_id)
        except Exception:
            continue
        if mid is None:
            continue

        ledger.update_mark(pos["condition_id"], mid)

        if mid < exit_threshold:
            continue

        ledger.close_position(pos["condition_id"], sell_price=round(mid, 2))
        closed += 1
        profit = round((mid - pos["price"]) * pos["size"], 2)
        print(f"    [PAPER EXIT] {pos['question'][:50]}... @ {mid:.2f} (profit ~${profit})")

    return closed
