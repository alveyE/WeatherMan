"""Shared data models for WeatherMan."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ScannedMarket:
    """Market data from Agent-01 scanner."""

    condition_id: str
    question: str
    yes_token_id: str
    no_token_id: str
    yes_mid: float
    no_mid: float
    volume_24hr: float
    liquidity: float
    end_date_iso: Optional[str]
    event_title: str
    event_id: Optional[str] = None
    # Parsed fields (may be None if unparseable)
    location: Optional[str] = None
    weather_type: Optional[str] = None
    target_date: Optional[str] = None
    coords: Optional[tuple[float, float]] = None  # (lat, lon) for NOAA
    threshold_low: Optional[float] = None
    threshold_high: Optional[float] = None


@dataclass
class Signal:
    """Trading signal from Agent-02 (paper or live)."""

    condition_id: str
    question: str
    token_id: str
    side: str  # "BUY_YES" or "BUY_NO"
    market_price: float
    fair_value: float
    edge_pct: float
    confidence: float
    event_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
