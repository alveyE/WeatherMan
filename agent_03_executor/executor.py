"""Agent-03: Execute trades on Polymarket CLOB."""

from agent_01_scanner.clob import get_mid_price
from shared.ledger import Ledger
from shared.models import Signal

from .client import get_client


def execute_signal(
    signal: Signal,
    max_exposure: float,
    max_per_trade_usd: float,
    ledger: Ledger,
) -> bool:
    """
    Execute a BUY signal if within risk limits.
    Returns True if order was placed, False otherwise.
    """
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

    try:
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY

        client = get_client()

        order = OrderArgs(
            token_id=signal.token_id,
            price=round(price, 2),
            size=size,
            side=BUY,
        )
        signed = client.create_order(order)
        client.post_order(signed, OrderType.GTC)

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
    except Exception as e:
        print(f"    [EXEC ERROR] {e}")
        return False


def check_exits(ledger: Ledger, exit_threshold: float) -> int:
    """
    Scan open positions; sell any whose current market price >= exit_threshold.
    Returns number of positions closed.
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
        if mid < exit_threshold:
            continue

        size = pos["size"]
        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import SELL

            client = get_client()
            order = OrderArgs(
                token_id=token_id,
                price=round(mid, 2),
                size=size,
                side=SELL,
            )
            signed = client.create_order(order)
            client.post_order(signed, OrderType.GTC)

            ledger.close_position(pos["condition_id"], sell_price=round(mid, 2))
            closed += 1
            profit = round((mid - pos["price"]) * size, 2)
            print(f"    EXIT {pos['question'][:50]}... @ {mid:.2f} (profit ~${profit})")
        except Exception as e:
            print(f"    [EXIT ERROR] {e}")

    return closed
