"""Geographic helpers. Keep Amap GCJ-02 coordinates; do not convert."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0
# Duplicate geocodes of the same POI, not a "nearby places are the same" merge.
SAME_POINT_M = 30.0


def normalize_city(name: str) -> str:
    text = (name or "").strip()
    for suffix in ("特别行政区", "壮族自治区", "回族自治区", "维吾尔自治区", "自治区", "省", "市"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break
    return text


def same_city(left: str, right: str) -> bool:
    a = normalize_city(left)
    b = normalize_city(right)
    return bool(a) and bool(b) and a == b


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def midpoint(lon1: float, lat1: float, lon2: float, lat2: float) -> tuple[float, float]:
    return ((lon1 + lon2) / 2.0, (lat1 + lat2) / 2.0)
