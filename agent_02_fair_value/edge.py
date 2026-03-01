"""Compute fair value and edge from NOAA data."""

from shared.models import ScannedMarket, Signal

from .noaa import avg_pop_for_month, get_forecast, pop_value


def compute_fair_value(market: ScannedMarket) -> float | None:
    """
    Compute fair value (0-1) for YES based on NOAA data.
    Returns None if we can't map this market to NOAA.
    """
    if not market.coords:
        return None

    lat, lon = market.coords
    periods = get_forecast(lat, lon)
    if not periods:
        return None

    weather_type = market.weather_type or ""
    target_date = market.target_date or ""

    # Precipitation: use PoP
    if "precipitation" in weather_type or "precip" in weather_type or "rain" in weather_type:
        if target_date:
            parts = target_date.split("-")
            if len(parts) >= 2:
                year, month = int(parts[0]), int(parts[1])
                avg_pop = avg_pop_for_month(periods, year, month)
                if avg_pop is None:
                    return None  # No forecast data (e.g. month already passed)
                return avg_pop / 100.0
        # No specific date: use average of next 7 days
        avg = sum(pop_value(p) for p in periods) / max(len(periods), 1)
        return avg / 100.0

    # Temperature: we'd need to parse "hit 90°F" etc - skip for now
    # Hurricane, sea ice: different data sources - skip for now
    return None


def find_signals(
    markets: list[ScannedMarket],
    edge_threshold_pct: float = 10.0,
) -> list[Signal]:
    """
    For each market, compute fair value and emit signal if edge > threshold.
    Paper mode: no execution, just return signals.
    """
    signals = []
    for m in markets:
        fair = compute_fair_value(m)
        if fair is None:
            continue

        market_yes = m.yes_mid
        edge = fair - market_yes
        edge_pct = abs(edge) * 100

        if edge_pct < edge_threshold_pct:
            continue

        # Signal: buy YES if fair > market, buy NO if fair < market
        if edge > 0:
            side = "BUY_YES"
            token_id = m.yes_token_id
        else:
            side = "BUY_NO"
            token_id = m.no_token_id
            fair = 1 - fair  # For NO, fair value of NO = 1 - fair_yes

        signals.append(
            Signal(
                condition_id=m.condition_id,
                question=m.question,
                token_id=token_id,
                side=side,
                market_price=market_yes if side == "BUY_YES" else m.no_mid,
                fair_value=fair,
                edge_pct=edge_pct,
                confidence=min(edge_pct / 20.0, 1.0),  # Simple confidence
            )
        )
    return signals
