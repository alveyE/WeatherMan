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
    max_slippage: float = 0.03,
) -> bool:
    """
    Execute a BUY signal if within risk limits.
    Uses a market order (FOK) with worst-price = scan price + max_slippage so we get filled
    as long as the ask is within a few cents of the scanned price.
    Returns True if order was placed and filled, False otherwise.
    """
    if ledger.has_traded(signal.condition_id):
        return False
    if signal.event_id and ledger.has_traded_event(signal.event_id):
        return False

    current = ledger.total_exposure()
    scan_price = signal.market_price

    size_usd = min(max_per_trade_usd, max_exposure - current)
    if size_usd < 0.5:
        return False

    # Worst price we're willing to pay (slippage cap)
    worst_price = min(0.99, round(scan_price + max_slippage, 2))
    size = round(size_usd / worst_price, 2)
    if size < 0.1:
        return False

    cost = worst_price * size
    if current + cost > max_exposure:
        return False

    try:
        from py_clob_client.clob_types import MarketOrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY

        client = get_client()

        # Market buy: FOK = fill entirely at or below worst_price, or cancel
        # options=None so client resolves tick_size and neg_risk from the API
        order = client.create_market_order(
            MarketOrderArgs(
                token_id=signal.token_id,
                side=BUY,
                amount=round(size_usd, 2),
                price=worst_price,
                order_type=OrderType.FOK,
            ),
            options=None,
        )
        response = client.post_order(order, OrderType.FOK)

        # Record using worst_price; actual fill may be slightly better
        ledger.record_trade(
            condition_id=signal.condition_id,
            token_id=signal.token_id,
            side=signal.side,
            price=worst_price,
            size=size,
            question=signal.question,
            event_id=signal.event_id,
            end_date_iso=signal.end_date_iso,
        )
        status = response.get("status", "unknown")
        print(f"    [FILLED] @ ≤{worst_price:.2f} (status: {status})")
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
