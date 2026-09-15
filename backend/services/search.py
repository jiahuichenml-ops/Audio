"""Midpoint POI search. Distances are to the geographic midpoint, not travel time."""

from __future__ import annotations

import logging
from typing import Any

from config import settings
from exceptions import AppError
from services.amap import amap_text, geocode_address, parse_distance_m, parse_location, search_around
from services.geo import haversine_m, midpoint, same_city
from services.storage import new_search_id, save_search_record

logger = logging.getLogger("meetup")
STAGE = "search"

# Approximate Hangzhou East / Longxiangqiao points for local mock only.
_MOCK_POINT_A = (120.212000, 30.291000)
_MOCK_POINT_B = (120.165000, 30.260000)


def mock_search(payload: dict[str, str]) -> dict[str, Any]:
    logger.info("stage=search mock=1")
    lon, lat = midpoint(*_MOCK_POINT_A, *_MOCK_POINT_B)
    demo = [
        {"name": "星巴克咖啡(模拟店)", "address": "杭州市上城区模拟路1号", "lon": lon + 0.001, "lat": lat},
        {"name": "瑞幸咖啡(模拟店)", "address": "杭州市西湖区模拟路8号", "lon": lon - 0.002, "lat": lat + 0.001},
        {"name": "Manner Coffee(模拟店)", "address": "杭州市西湖区模拟街12号", "lon": lon, "lat": lat - 0.0015},
    ]
    pois = []
    for item in demo:
        distance = round(haversine_m(lon, lat, item["lon"], item["lat"]))
        pois.append(
            {
                "name": item["name"],
                "address": item["address"],
                "distance_to_midpoint_m": distance,
            }
        )
    pois.sort(key=lambda row: row["distance_to_midpoint_m"])
    record = {
        "city_a": payload["city_a"],
        "address_a": payload["address_a"],
        "city_b": payload["city_b"],
        "address_b": payload["address_b"],
        "category": payload["category"],
        "point_a": {"longitude": _MOCK_POINT_A[0], "latitude": _MOCK_POINT_A[1]},
        "point_b": {"longitude": _MOCK_POINT_B[0], "latitude": _MOCK_POINT_B[1]},
        "midpoint": {"longitude": lon, "latitude": lat},
        "pois": pois,
        "radius_m": 2000,
        "mock": True,
    }
    search_id = new_search_id()
    save_search_record(search_id, record)
    return {
        "search_id": search_id,
        "midpoint": {"longitude": lon, "latitude": lat},
        "pois": pois,
    }


def _poi_row(item: dict[str, Any], mid_lon: float, mid_lat: float) -> dict[str, Any] | None:
    name = amap_text(item.get("name"))
    address = amap_text(item.get("address"))
    if not name or not address:
        return None
    point = parse_location(item.get("location"))
    distance = parse_distance_m(item.get("distance"))
    if distance is None:
        if point is None:
            return None
        distance = haversine_m(mid_lon, mid_lat, point[0], point[1])
    return {
        "name": name,
        "address": address,
        "distance_to_midpoint_m": int(round(distance)),
    }


async def search_meetup(payload: dict[str, str]) -> dict[str, Any]:
    if not same_city(payload["city_a"], payload["city_b"]):
        raise AppError(
            422,
            "CROSS_CITY",
            "目前只支持同一座城市内的两人碰面，请改成同城地点后再试。",
            STAGE,
        )
    if settings.search_mock:
        return mock_search(payload)

    point_a = await geocode_address(payload["city_a"], payload["address_a"])
    point_b = await geocode_address(payload["city_b"], payload["address_b"])
    mid_lon, mid_lat = midpoint(point_a[0], point_a[1], point_b[0], point_b[1])

    pois: list[dict[str, Any]] = []
    used_radius = 2000
    for radius in (2000, 5000):
        raw = await search_around(mid_lon, mid_lat, payload["category"], payload["city_a"], radius)
        rows = []
        for item in raw:
            row = _poi_row(item, mid_lon, mid_lat)
            if row is not None:
                rows.append(row)
        rows.sort(key=lambda row: row["distance_to_midpoint_m"])
        pois = rows[:3]
        used_radius = radius
        if pois:
            break
    if not pois:
        raise AppError(
            422,
            "NO_CANDIDATES",
            "中点附近没有找到合适的店，请换个地点或类别后再试。",
            STAGE,
        )

    search_id = new_search_id()
    save_search_record(
        search_id,
        {
            "city_a": payload["city_a"],
            "address_a": payload["address_a"],
            "city_b": payload["city_b"],
            "address_b": payload["address_b"],
            "category": payload["category"],
            "point_a": {"longitude": point_a[0], "latitude": point_a[1]},
            "point_b": {"longitude": point_b[0], "latitude": point_b[1]},
            "midpoint": {"longitude": mid_lon, "latitude": mid_lat},
            "pois": pois,
            "radius_m": used_radius,
        },
    )
    logger.info(
        "stage=search ok search_id=%s poi_count=%s radius_m=%s",
        search_id,
        len(pois),
        used_radius,
    )
    return {
        "search_id": search_id,
        "midpoint": {"longitude": mid_lon, "latitude": mid_lat},
        "pois": pois,
    }
