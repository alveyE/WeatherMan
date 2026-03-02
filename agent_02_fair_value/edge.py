"""Compute fair value and edge from NOAA data."""

import math

from shared.models import ScannedMarket, Signal

from .noaa import get_forecast_temperature_f, get_qpf_total_inches

# ---------------------------------------------------------------------------
# Probability helpers (pure math, no scipy needed)
# ---------------------------------------------------------------------------

PRECIP_LOG_SIGMA = 0.6  # log-normal shape parameter for QPF uncertainty
TEMP_SIGMA_F = 3.5  # forecast stddev in Fahrenheit for 1-2 day forecasts


def _normal_cdf(x: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    """Standard-library normal CDF via math.erf."""
    return 0.5 * (1.0 + math.erf((x - mu) / (sigma * math.sqrt(2))))


def _prob_precip_exceeds(threshold_inches: float, qpf_inches: float) -> float:
    """
    P(actual precipitation > threshold) given NOAA QPF forecast.
    Models actual precip as log-normal with median = qpf and
    shape σ = PRECIP_LOG_SIGMA.  Returns probability in [0, 1].
    """
    if threshold_inches <= 0:
        return 1.0 if qpf_inches > 0 else 0.5
    if qpf_inches <= 0:
        return 0.0

    mu = math.log(qpf_inches)
    z = (math.log(threshold_inches) - mu) / PRECIP_LOG_SIGMA
    return 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


def _prob_temp_in_range(
    forecast_f: float,
    low: float | None,
    high: float | None,
) -> float:
    """
    P(temperature falls in [low, high]) given NOAA forecast temp.
    Models actual temp as N(forecast_f, TEMP_SIGMA_F²).
    """
    if low is not None and high is not None:
        return _normal_cdf(high, forecast_f, TEMP_SIGMA_F) - _normal_cdf(low, forecast_f, TEMP_SIGMA_F)
    if low is not None:
        return 1.0 - _normal_cdf(low, forecast_f, TEMP_SIGMA_F)
    if high is not None:
        return _normal_cdf(high, forecast_f, TEMP_SIGMA_F)
    return 0.5


# ---------------------------------------------------------------------------
# Fair value
# ---------------------------------------------------------------------------

def compute_fair_value(market: ScannedMarket) -> float | None:
    """
    Compute fair value (0-1) for YES based on NOAA data.
    Returns None if we can't map this market to NOAA.
    """
    if not market.coords:
        return None

    lat, lon = market.coords
    weather_type = market.weather_type or ""

    # --- Precipitation: QPF + log-normal model ---
    if weather_type == "precipitation":
        if market.threshold_low is None:
            return None
        qpf = get_qpf_total_inches(lat, lon, window_hours=48)
        if qpf is None:
            return None
        return _prob_precip_exceeds(market.threshold_low, qpf)

    # --- Temperature: forecast temp + normal model ---
    if weather_type == "temperature":
        if market.threshold_low is None and market.threshold_high is None:
            return None
        target_iso = None
        if market.target_date and len(market.target_date) >= 10:
            target_iso = market.target_date[:10]
        elif market.end_date_iso and len(market.end_date_iso) >= 10:
            target_iso = market.end_date_iso[:10]
        if target_iso is None:
            return None
        forecast_f = get_forecast_temperature_f(lat, lon, target_date=target_iso)
        if forecast_f is None:
            return None
        return _prob_temp_in_range(forecast_f, market.threshold_low, market.threshold_high)

    return None


# ---------------------------------------------------------------------------
# Signal generation (with per-event dedup)
# ---------------------------------------------------------------------------

def find_signals(
    markets: list[ScannedMarket],
    edge_threshold_pct: float = 10.0,
    entry_threshold: float = 1.0,
    min_price: float = 0.04,
) -> list[Signal]:
    """
    For each market compute fair value, emit signal if edge > threshold
    and min_price <= market price <= entry_threshold, then keep only the
    single best signal per event.
    """
    raw_signals: list[Signal] = []

    for m in markets:
        fair = compute_fair_value(m)
        if fair is None:
            continue

        market_yes = m.yes_mid
        edge = fair - market_yes
        edge_pct = abs(edge) * 100

        if edge_pct < edge_threshold_pct:
            continue

        if edge > 0:
            side = "BUY_YES"
            token_id = m.yes_token_id
            price = market_yes
        else:
            side = "BUY_NO"
            token_id = m.no_token_id
            price = m.no_mid
            fair = 1 - fair

        if price < min_price or price > entry_threshold:
            continue

        raw_signals.append(
            Signal(
                condition_id=m.condition_id,
                question=m.question,
                token_id=token_id,
                side=side,
                market_price=price,
                fair_value=fair,
                edge_pct=edge_pct,
                confidence=min(edge_pct / 20.0, 1.0),
                event_id=m.event_id,
            )
        )

    # Deduplicate: keep only the highest-edge signal per event
    best_by_event: dict[str, Signal] = {}
    no_event: list[Signal] = []

    for sig in raw_signals:
        key = sig.event_id
        if not key:
            no_event.append(sig)
            continue
        existing = best_by_event.get(key)
        if existing is None or sig.edge_pct > existing.edge_pct:
            best_by_event[key] = sig

    return list(best_by_event.values()) + no_event
