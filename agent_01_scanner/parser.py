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


def parse_question(question: str) -> dict:
    """
    Extract location, weather_type, target_date from market question.
    Returns dict with keys that may be None if not found.
    """
    q = question.lower().strip()
    result = {"location": None, "weather_type": None, "target_date": None, "coords": None}

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

    # Target date: month names, "February", "March", etc.
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    }
    for month_name, num in months.items():
        if month_name in q:
            # Default to current year
            year = datetime.utcnow().year
            # Check for year in question (e.g. "February 2026")
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
