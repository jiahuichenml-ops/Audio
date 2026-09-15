"""Amap geocode and around-search. Never log the API key."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import settings
from exceptions import AppError
from services.geo import SAME_POINT_M, haversine_m, normalize_city

logger = logging.getLogger("meetup")
STAGE = "search"
COARSE_LEVELS = {"国家", "省", "市", "区县", "开发区", "乡镇", "村庄", "未知"}


def amap_text(value: object) -> str:
    if value is None or isinstance(value, list):
        return ""
    return str(value).strip()


def parse_location(value: object) -> tuple[float, float] | None:
    text = amap_text(value)
    if "," not in text:
        return None
    left, right = text.split(",", 1)
    try:
        longitude = float(left.strip())
        latitude = float(right.strip())
    except ValueError:
        return None
    if not (-180.0 <= longitude <= 180.0 and -90.0 <= latitude <= 90.0):
        return None
    return longitude, latitude


def parse_distance_m(value: object) -> float | None:
    text = amap_text(value)
    if not text:
        return None
    try:
        distance = float(text)
    except ValueError:
        return None
    if distance < 0:
        return None
    return distance


def _city_of(geocode: dict[str, Any]) -> str:
    return amap_text(geocode.get("city")) or amap_text(geocode.get("province"))


def _matches_requested_city(geocode: dict[str, Any], requested_city: str) -> bool:
    wanted = normalize_city(requested_city)
    if not wanted:
        return False
    actual = normalize_city(_city_of(geocode))
    formatted = amap_text(geocode.get("formatted_address"))
    return actual == wanted or wanted in formatted


def _strip_city_prefix(address: str, city: str) -> str:
    text = address.strip()
    prefixes = [city.strip(), normalize_city(city)]
    prefixes.extend([item + "市" for item in prefixes if item and not item.endswith("市")])
    for prefix in sorted({item for item in prefixes if item}, key=len, reverse=True):
        if text.startswith(prefix) and len(text) > len(prefix):
            return text[len(prefix) :].lstrip("市")
    return text


def _name_matches(geocode: dict[str, Any], address: str, city: str) -> bool:
    query = address.strip()
    if not query:
        return False
    haystack = "".join(
        [
            amap_text(geocode.get("formatted_address")),
            amap_text(geocode.get("district")),
            amap_text(geocode.get("street")),
            amap_text(geocode.get("number")),
            amap_text(geocode.get("township")),
        ]
    )
    if query in haystack:
        return True
    distinctive = _strip_city_prefix(query, city)
    if distinctive in haystack:
        return True
    source = distinctive if len(distinctive) >= 3 else query
    for size in range(min(len(source), 6), 2, -1):
        for index in range(0, len(source) - size + 1):
            if source[index : index + size] in haystack:
                return True
    return False


def pick_geocode(geocodes: list[dict[str, Any]], city: str, address: str) -> dict[str, Any]:
    filtered: list[dict[str, Any]] = []
    for item in geocodes:
        if not isinstance(item, dict):
            continue
        if amap_text(item.get("level")) in COARSE_LEVELS:
            continue
        if parse_location(item.get("location")) is None:
            continue
        if not _matches_requested_city(item, city):
            continue
        if not _name_matches(item, address, city):
            continue
        filtered.append(item)
    if not filtered:
        raise AppError(
            422,
            "LOCATION_AMBIGUOUS",
            "无法明确这两个地点，请说得更具体一些后再试。",
            STAGE,
        )
    if len(filtered) == 1:
        return filtered[0]
    # Only collapse exact duplicates. Different POIs within 300m stay ambiguous.
    first = parse_location(filtered[0].get("location"))
    assert first is not None
    all_same_point = True
    for item in filtered[1:]:
        point = parse_location(item.get("location"))
        if point is None or haversine_m(first[0], first[1], point[0], point[1]) > SAME_POINT_M:
            all_same_point = False
            break
    if all_same_point:
        return filtered[0]
    raise AppError(
        422,
        "LOCATION_AMBIGUOUS",
        "找到多个可能的地点，无法可靠区分，请补充更具体的地名后再试。",
        STAGE,
    )


async def _amap_get(url: str, params: dict[str, str]) -> dict[str, Any]:
    api_key = settings.amap_api_key.strip()
    if not api_key:
        raise AppError(
            502,
            "SEARCH_NOT_CONFIGURED",
            "未配置高德密钥，无法查询地点。请在 backend/.env 填写 AMAP_API_KEY 后重启服务。",
            STAGE,
        )
    query = {"key": api_key, "output": "json", **params}
    timeout = httpx.Timeout(
        connect=5.0,
        read=settings.amap_timeout_s,
        write=10.0,
        pool=5.0,
    )
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=query)
    except httpx.TimeoutException as exc:
        logger.info("stage=search timeout url_kind=%s", "geo" if "geocode" in url else "around")
        raise AppError(
            504,
            "SEARCH_TIMEOUT",
            "地点查询超时，请稍后重试。",
            STAGE,
        ) from exc
    except httpx.HTTPError as exc:
        logger.info("stage=search http_error type=%s", type(exc).__name__)
        raise AppError(
            502,
            "SEARCH_UPSTREAM",
            "地点查询服务暂时不可用，请稍后重试。",
            STAGE,
        ) from exc
    if response.status_code >= 500:
        logger.info("stage=search upstream_http=%s", response.status_code)
        raise AppError(
            502,
            "SEARCH_UPSTREAM",
            "地点查询服务暂时不可用，请稍后重试。",
            STAGE,
        )
    if response.status_code >= 400:
        logger.info("stage=search upstream_http=%s", response.status_code)
        raise AppError(
            502,
            "SEARCH_UPSTREAM",
            "地点查询失败，请稍后重试。",
            STAGE,
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise AppError(
            502,
            "SEARCH_UPSTREAM",
            "地点查询服务返回无法解析的结果，请稍后重试。",
            STAGE,
        ) from exc
    if not isinstance(body, dict):
        raise AppError(
            502,
            "SEARCH_UPSTREAM",
            "地点查询服务返回无法解析的结果，请稍后重试。",
            STAGE,
        )
    status = amap_text(body.get("status"))
    info = amap_text(body.get("info"))
    infocode = amap_text(body.get("infocode"))
    if status != "1":
        logger.info("stage=search amap_status=%s infocode=%s", status, infocode)
        if infocode in {"10001", "10003", "10009", "10004"} or "INVALID_USER_KEY" in info:
            raise AppError(
                502,
                "SEARCH_UNAUTHORIZED",
                "高德密钥无效或没有 Web 服务权限，请检查后重试。",
                STAGE,
            )
        raise AppError(
            502,
            "SEARCH_UPSTREAM",
            "地点查询失败，请稍后重试。",
            STAGE,
        )
    return body


async def geocode_address(city: str, address: str) -> tuple[float, float]:
    body = await _amap_get(
        settings.amap_geocode_url,
        {"address": address.strip(), "city": city.strip()},
    )
    raw = body.get("geocodes") or []
    if not isinstance(raw, list) or not raw:
        raise AppError(
            422,
            "LOCATION_AMBIGUOUS",
            "无法明确这两个地点，请说得更具体一些后再试。",
            STAGE,
        )
    chosen = pick_geocode([item for item in raw if isinstance(item, dict)], city, address)
    point = parse_location(chosen.get("location"))
    if point is None:
        raise AppError(
            422,
            "LOCATION_AMBIGUOUS",
            "无法明确这两个地点，请说得更具体一些后再试。",
            STAGE,
        )
    return point


async def search_around(
    longitude: float,
    latitude: float,
    keywords: str,
    city: str,
    radius_m: int,
) -> list[dict[str, Any]]:
    location = f"{longitude:.6f},{latitude:.6f}"
    body = await _amap_get(
        settings.amap_place_around_url,
        {
            "location": location,
            "keywords": keywords.strip(),
            "radius": str(radius_m),
            "city": city.strip(),
            "citylimit": "true",
            "offset": "25",
            "page": "1",
            "extensions": "base",
        },
    )
    raw = body.get("pois") or []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]
