"""Geocoding helpers.

Two jobs:
  1. haversine() great-circle distance — the reciprocal-program distance rules are
     explicitly *linear radius*, not driving distance, so this is the correct metric.
  2. ZIP -> lat/lng via the bundled ZCTA centroid table (no per-request API calls).

A thin Nominatim wrapper is provided for *future* expansion (geocoding new institution
addresses when the metro frontier grows). The Phase-1 seed set ships with hand-verified
coordinates, so the pipeline does not depend on a live geocoder.
"""
from __future__ import annotations

import csv
import math
import os
from functools import lru_cache
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
ZCTA_CSV = os.path.join(DATA_DIR, "zcta_centroids.csv")

EARTH_RADIUS_MILES = 3958.7613


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in miles between two (lat, lng) points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def _zcta_table() -> dict[str, tuple[float, float]]:
    table: dict[str, tuple[float, float]] = {}
    with open(ZCTA_CSV, newline="") as f:
        for row in csv.DictReader(f):
            table[row["zip"]] = (float(row["lat"]), float(row["lng"]))
    return table


def zip_to_latlng(zip_code: str) -> Optional[tuple[float, float]]:
    """Return (lat, lng) centroid for a 5-digit ZIP, or None if not in the table."""
    z = (zip_code or "").strip()[:5]
    return _zcta_table().get(z)


def nominatim_geocode(address: str, user_agent: str) -> Optional[tuple[float, float]]:
    """Geocode a free-form address via OpenStreetMap Nominatim. Future-expansion only;
    honor Nominatim's usage policy (1 req/s, descriptive UA). Returns (lat, lng) or None."""
    import httpx  # local import: not needed for the hand-verified seed set

    resp = httpx.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": address, "format": "json", "limit": 1},
        headers={"User-Agent": user_agent},
        timeout=30,
    )
    resp.raise_for_status()
    hits = resp.json()
    if not hits:
        return None
    return float(hits[0]["lat"]), float(hits[0]["lon"])
