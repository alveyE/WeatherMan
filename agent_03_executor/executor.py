"""Agent-03: Execute trades on Polymarket CLOB."""

from pathlib import Path

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
    Execute a signal if within risk limits.
    Returns True if order was placed, False otherwise.
    """
    if ledger.has_traded(signal.condition_id):
        return False  # Already have position

    current = ledger.total_exposure()
    price = signal.market_price

    # Size: spend up to max_per_trade_usd
    size_usd = min(max_per_trade_usd, max_exposure - current)
    if size_usd < 0.5:  # Min $0.50 per trade
        return False

    # Shares = USD / price. Round down to 2 decimals
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
            )
        return True
    except Exception as e:
        print(f"    [EXEC ERROR] {e}")
        return False
