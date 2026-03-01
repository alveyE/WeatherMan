"""Track trades and exposure for balance cap."""

import json
from datetime import datetime
from pathlib import Path


class Ledger:
    """Simple file-based ledger for tracking trades and exposure."""

    def __init__(self, path: str | Path = "ledger.json"):
        self.path = Path(path)
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            with open(self.path) as f:
                return json.load(f)
        return {"trades": [], "initial_balance": 0}

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
    ):
        cost = price * size
        self._data["trades"].append({
            "condition_id": condition_id,
            "token_id": token_id,
            "side": side,
            "price": price,
            "size": size,
            "cost_usd": round(cost, 2),
            "question": question[:80],
            "timestamp": datetime.utcnow().isoformat(),
        })
        self._save()

    def total_exposure(self) -> float:
        """Sum of cost for all trades (conservative: no resolution tracking)."""
        return sum(t["cost_usd"] for t in self._data["trades"])

    def has_traded(self, condition_id: str) -> bool:
        """Check if we've already traded this market."""
        return any(t["condition_id"] == condition_id for t in self._data["trades"])

    def trade_count(self) -> int:
        return len(self._data["trades"])
