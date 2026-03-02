"""Fetch NOAA/NWS forecast data (7-day periods and raw gridpoint QPF/temp)."""

import re
import requests
from datetime import datetime, timedelta, timezone
from functools import lru_cache

NWS_BASE = "https://api.weather.gov"
USER_AGENT = "(WeatherMan/1.0, weather-arb-bot)"

MM_PER_INCH = 25.4


# ---------------------------------------------------------------------------
# Low-level: /points metadata (cached per coordinate pair)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _get_point_metadata(lat: float, lon: float) -> dict | None:
    """Fetch and cache /points metadata for a rounded (lat, lon)."""
    resp = requests.get(
        f"{NWS_BASE}/points/{lat},{lon}",
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    return resp.json().get("properties", {})


def _round_coords(lat: float, lon: float) -> tuple[float, float]:
    return round(lat, 4), round(lon, 4)


# ---------------------------------------------------------------------------
# 7-day textual forecast (existing, used for temperature periods)
# ---------------------------------------------------------------------------

def get_forecast(lat: float, lon: float) -> list[dict] | None:
    """
    Get 7-day forecast periods for a location.
    Each period has startTime, temperature, probabilityOfPrecipitation, etc.
    """
    lat, lon = _round_coords(lat, lon)
    props = _get_point_metadata(lat, lon)
    if not props:
        return None

    forecast_url = props.get("forecast")
    if not forecast_url:
        return None

    resp = requests.get(
        forecast_url,
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    if resp.status_code != 200:
        return None

    return resp.json().get("properties", {}).get("periods", [])


# ---------------------------------------------------------------------------
# Raw gridpoint data (/gridpoints) — QPF and hourly temperature
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _get_gridpoint_properties(lat: float, lon: float) -> dict | None:
    """Fetch raw gridpoint forecast data (QPF, temperature, etc.)."""
    lat, lon = _round_coords(lat, lon)
    props = _get_point_metadata(lat, lon)
    if not props:
        return None

    grid_url = props.get("forecastGridData")
    if not grid_url:
        return None

    resp = requests.get(
        grid_url,
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    if resp.status_code != 200:
        return None

    return resp.json().get("properties", {})


def _parse_valid_time(valid_time: str) -> tuple[datetime, timedelta] | None:
    """
    Parse NWS validTime format: '2026-03-01T06:00:00+00:00/PT6H'
    Returns (start_dt, duration) or None.
    """
    parts = valid_time.split("/")
    if len(parts) != 2:
        return None
    try:
        start = datetime.fromisoformat(parts[0].replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None

    dur_str = parts[1]
    hours = 0
    h_match = re.search(r"(\d+)H", dur_str)
    if h_match:
        hours += int(h_match.group(1))
    d_match = re.search(r"(\d+)D", dur_str)
    if d_match:
        hours += int(d_match.group(1)) * 24
    duration = timedelta(hours=max(hours, 1))

    return start, duration


# ---------------------------------------------------------------------------
# QPF helpers (Quantitative Precipitation Forecast)
# ---------------------------------------------------------------------------

def get_qpf_total_inches(
    lat: float,
    lon: float,
    window_hours: int = 48,
) -> float | None:
    """
    Sum QPF over the next *window_hours* from the NWS gridpoint data.
    Returns total expected precipitation in **inches**, or None on error.
    """
    grid = _get_gridpoint_properties(lat, lon)
    if not grid:
        return None

    qpf_data = grid.get("quantitativePrecipitation", {}).get("values", [])
    if not qpf_data:
        return None

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=window_hours)
    total_mm = 0.0

    for entry in qpf_data:
        parsed = _parse_valid_time(entry.get("validTime", ""))
        if not parsed:
            continue
        start, dur = parsed
        end = start + dur
        if end <= now or start >= cutoff:
            continue
        val = entry.get("value")
        if val is not None:
            total_mm += float(val)

    return total_mm / MM_PER_INCH


# ---------------------------------------------------------------------------
# Temperature helpers
# ---------------------------------------------------------------------------

def get_forecast_temperature_f(
    lat: float,
    lon: float,
    target_date: str | None = None,
) -> float | None:
    """
    Return the forecast high temperature in Fahrenheit for *target_date*
    (ISO date string like '2026-03-02').
    Returns None if target_date is not provided or no matching period found.
    """
    if not target_date:
        return None

    periods = get_forecast(lat, lon)
    if not periods:
        return None

    for p in periods:
        if not p.get("isDaytime", False):
            continue
        start_str = p.get("startTime", "")
        try:
            dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        if dt.strftime("%Y-%m-%d") == target_date:
            return float(p["temperature"])

    return None


# ---------------------------------------------------------------------------
# Legacy helpers (kept for backward compat, no longer used in fair value)
# ---------------------------------------------------------------------------

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
