"""Parse market questions into location, weather_type, target_date."""

import re
from datetime import datetime

# City -> (lat, lon) for common weather market locations
CITY_COORDS = {
    "nyc": (40.7128, -74.0060),
    "new york": (40.7128, -74.0060),
    "new york city": (40.7128, -74.0060),
    "seattle": (47.6062, -122.3321),
    "austin": (30.2672, -97.7431),
    "houston": (29.7604, -95.3698),
    "dallas": (32.7767, -96.7970),
    "chicago": (41.8781, -87.6298),
    "la": (34.0522, -118.2437),
    "los angeles": (34.0522, -118.2437),
    "miami": (25.7617, -80.1918),
    "phoenix": (33.4484, -112.0740),
    "boston": (42.3601, -71.0589),
    "denver": (39.7392, -104.9903),
    "texas": (31.9686, -99.9018),  # centroid
}


def _parse_thresholds(q: str, weather_type: str | None) -> tuple[float | None, float | None]:
    """Extract numeric threshold_low and threshold_high from a question string."""
    low, high = None, None

    if weather_type == "precipitation":
        # "3+ inches", "3 or more inches", "at least 3 inches"
        m = re.search(r"(\d+\.?\d*)\s*\+\s*inch", q)
        if m:
            return float(m.group(1)), None
        m = re.search(r"(?:at least|or more than?|over|above|more than|exceed)\s*(\d+\.?\d*)\s*inch", q)
        if m:
            return float(m.group(1)), None
        # "between 4 and 5 inches", "4 to 5 inches", "4-5 inches"
        m = re.search(r"(?:between\s+)?(\d+\.?\d*)\s*(?:and|to|-)\s*(\d+\.?\d*)\s*inch", q)
        if m:
            return float(m.group(1)), float(m.group(2))
        # "under 2 inches", "less than 2 inches"
        m = re.search(r"(?:under|less than|below|fewer than)\s*(\d+\.?\d*)\s*inch", q)
        if m:
            return None, float(m.group(1))

    elif weather_type == "temperature":
        # "between 28-29°F", "between 28 and 29", "40 to 45 degrees"
        m = re.search(r"(?:between\s+)?(\d+)\s*(?:and|to|-)\s*(\d+)\s*(?:°|degree|f\b)", q)
        if m:
            return float(m.group(1)), float(m.group(2))
        # "27°f or below", "32°f or lower"
        m = re.search(r"(\d+)\s*°?\s*f?\s*or\s+(?:below|lower|less)", q)
        if m:
            return None, float(m.group(1))
        # "50°f or above", "50°f or higher"
        m = re.search(r"(\d+)\s*°?\s*f?\s*or\s+(?:above|higher|more)", q)
        if m:
            return float(m.group(1)), None
        # "hit 90°F", "reach 90", "above 90", "over 90", "at least 90"
        m = re.search(r"(?:hit|reach|above|over|exceed|at least)\s*(\d+)\s*(?:°|degree|f\b)?", q)
        if m:
            return float(m.group(1)), None
        # "below 32", "under 40"
        m = re.search(r"(?:below|under|less than)\s*(\d+)\s*(?:°|degree|f\b)?", q)
        if m:
            return None, float(m.group(1))
        # Bare range: "40-45" anywhere
        m = re.search(r"(\d+)\s*-\s*(\d+)", q)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            if 0 <= a <= 150 and 0 <= b <= 150:
                return a, b

    return low, high


def parse_question(question: str) -> dict:
    """
    Extract location, weather_type, target_date, and numeric thresholds
    from a market question.
    """
    q = question.lower().strip()
    result = {
        "location": None,
        "weather_type": None,
        "target_date": None,
        "coords": None,
        "threshold_low": None,
        "threshold_high": None,
    }

    # Location: check known cities (use word boundary for short names like "la")
    words = set(re.split(r"\W+", q))
    for city, coords in CITY_COORDS.items():
        if city in words or (len(city) > 3 and city in q):
            result["location"] = city.title()
            result["coords"] = coords
            break

    # Weather type
    if "rain" in q or "precip" in q or "precipitation" in q:
        result["weather_type"] = "precipitation"
    elif "snow" in q:
        result["weather_type"] = "snow"
    elif "hurricane" in q:
        result["weather_type"] = "hurricane"
    elif "temp" in q or "°" in q or "degree" in q or "hottest" in q:
        result["weather_type"] = "temperature"
    elif "arctic" in q or "sea ice" in q:
        result["weather_type"] = "sea_ice"

    # Numeric thresholds (e.g. "3+ inches", "40 to 45 degrees")
    low, high = _parse_thresholds(q, result["weather_type"])
    result["threshold_low"] = low
    result["threshold_high"] = high

    # Target date: month names, "February", "March", etc.
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    }
    for month_name, num in months.items():
        if month_name in q:
            year = datetime.utcnow().year
            year_match = re.search(r"20[2-3][0-9]", q)
            if year_match:
                year = int(year_match.group())
            result["target_date"] = f"{year}-{num:02d}"
            break

    # "by May 31" style
    by_match = re.search(r"by\s+(\w+)\s+(\d{1,2})", q)
    if by_match and not result["target_date"]:
        month_str, day = by_match.group(1), by_match.group(2)
        for month_name, num in months.items():
            if month_name.startswith(month_str[:3]):
                year = datetime.utcnow().year
                result["target_date"] = f"{year}-{num:02d}-{int(day):02d}"
                break

    return result
