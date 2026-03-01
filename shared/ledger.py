"""Track trades and exposure for balance cap."""

import json
from datetime import datetime
from pathlib import Path


class Ledger:
    """Simple file-based ledger for tracking trades and exposure."""

    def __init__(self, path: str | Path = "ledger.json"):
        self.path = Path(path)
        self._data = self._load()
        self._migrate()

    def _load(self) -> dict:
        if self.path.exists():
            with open(self.path) as f:
                return json.load(f)
        return {"trades": [], "initial_balance": 0}

    def _migrate(self):
        """Back-fill 'status' on legacy trades that lack it."""
        changed = False
        for t in self._data["trades"]:
            if "status" not in t:
                t["status"] = "open"
                changed = True
        if changed:
            self._save()

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2)

    def set_initial_balance(self, amount: float):
        self._data["initial_balance"] = amount
        self._save()

    def record_trade(
        self,
        condition_id: str,
        token_id: str,
        side: str,
        price: float,
        size: float,
        question: str,
        event_id: str | None = None,
    ):
        cost = price * size
        entry: dict = {
            "condition_id": condition_id,
            "token_id": token_id,
            "side": side,
            "price": price,
            "size": size,
            "cost_usd": round(cost, 2),
            "question": question[:80],
            "timestamp": datetime.utcnow().isoformat(),
            "status": "open",
        }
        if event_id:
            entry["event_id"] = event_id
        self._data["trades"].append(entry)
        self._save()

    def close_position(self, condition_id: str, sell_price: float):
        """Mark an open position as closed and record the exit price."""
        for t in self._data["trades"]:
            if t["condition_id"] == condition_id and t.get("status") == "open":
                t["status"] = "closed"
                t["sell_price"] = sell_price
                t["closed_at"] = datetime.utcnow().isoformat()
                break
        self._save()

    def open_positions(self) -> list[dict]:
        """Return all trades with status 'open'."""
        return [t for t in self._data["trades"] if t.get("status") == "open"]

    def total_exposure(self) -> float:
        """Sum of cost for open positions only."""
        return sum(t["cost_usd"] for t in self._data["trades"] if t.get("status") == "open")

    def has_traded(self, condition_id: str) -> bool:
        """Check if we have an open position on this sub-market."""
        return any(
            t["condition_id"] == condition_id and t.get("status") == "open"
            for t in self._data["trades"]
        )

    def has_traded_event(self, event_id: str) -> bool:
        """Check if we have an open position on any sub-market in this event."""
        if not event_id:
            return False
        return any(
            t.get("event_id") == event_id and t.get("status") == "open"
            for t in self._data["trades"]
        )

    def trade_count(self) -> int:
        return len(self._data["trades"])
