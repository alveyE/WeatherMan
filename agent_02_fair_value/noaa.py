"""Fetch NOAA/NWS forecast data."""

import requests
from datetime import datetime

NWS_BASE = "https://api.weather.gov"
USER_AGENT = "(WeatherMan/1.0, paper-trading-poc)"


def get_forecast(lat: float, lon: float) -> list[dict] | None:
    """
    Get 7-day forecast periods for a location.
    Returns list of period dicts with startTime, probabilityOfPrecipitation, temperature.
    """
    # Round coords to 4 decimals
    lat = round(lat, 4)
    lon = round(lon, 4)

    points_resp = requests.get(
        f"{NWS_BASE}/points/{lat},{lon}",
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    if points_resp.status_code != 200:
        return None

    props = points_resp.json().get("properties", {})
    forecast_url = props.get("forecast")
    if not forecast_url:
        return None

    forecast_resp = requests.get(
        forecast_url,
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    if forecast_resp.status_code != 200:
        return None

    periods = forecast_resp.json().get("properties", {}).get("periods", [])
    return periods


def pop_value(period: dict) -> float:
    """Extract probability of precipitation as 0-100."""
    pop = period.get("probabilityOfPrecipitation")
    if pop is None:
        return 0
    if isinstance(pop, (int, float)):
        return float(pop)
    if isinstance(pop, dict) and "value" in pop:
        return float(pop["value"] or 0)
    return 0


def periods_in_month(periods: list[dict], year: int, month: int) -> list[dict]:
    """Filter periods that fall within the given month."""
    result = []
    for p in periods:
        start = p.get("startTime")
        if not start:
            continue
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if dt.year == year and dt.month == month:
                result.append(p)
        except (ValueError, TypeError):
            continue
    return result


def avg_pop_for_month(periods: list[dict], year: int, month: int, min_periods: int = 4) -> float | None:
    """Average PoP for all periods in the given month. Returns 0-100, or None if insufficient data."""
    in_month = periods_in_month(periods, year, month)
    if len(in_month) < min_periods:
        return None  # Not enough forecast data (month mostly past or too far out)
    total = sum(pop_value(p) for p in in_month)
    return total / len(in_month)
