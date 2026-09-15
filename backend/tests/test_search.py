from unittest.mock import patch

from fastapi.testclient import TestClient

from exceptions import AppError
from main import app
from services.amap import pick_geocode
from services.geo import haversine_m, midpoint


SEARCH_BODY = {
    "city_a": "杭州",
    "address_a": "杭州东站",
    "city_b": "杭州",
    "address_b": "西湖龙翔桥地铁站",
    "category": "咖啡店",
}


def _client(tmp_path, monkeypatch, **overrides) -> TestClient:
    from config import settings

    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(settings, "search_mock", False)
    monkeypatch.setattr(settings, "amap_api_key", "amap-test")
    for key, value in overrides.items():
        monkeypatch.setattr(settings, key, value)
    return TestClient(app)


def test_search_returns_midpoint_and_sorted_pois(tmp_path, monkeypatch) -> None:
    async def fake_geocode(city: str, address: str):
        if "东站" in address:
            return (120.212, 30.291)
        return (120.165, 30.260)

    async def fake_around(lon, lat, keywords, city, radius_m):
        assert keywords == "咖啡店"
        return [
            {
                "name": "远的店",
                "address": "杭州市西湖区远路9号",
                "location": f"{lon + 0.01},{lat}",
                "distance": "900",
            },
            {
                "name": "近的店",
                "address": "杭州市上城区近路1号",
                "location": f"{lon + 0.001},{lat}",
                "distance": [],
            },
            {
                "name": "中间的店",
                "address": "杭州市西湖区中路3号",
                "location": f"{lon - 0.003},{lat}",
                "distance": "350",
            },
            {
                "name": "缺地址的店",
                "address": [],
                "location": f"{lon},{lat}",
                "distance": "10",
            },
        ]

    with patch("services.search.geocode_address", new=fake_geocode):
        with patch("services.search.search_around", new=fake_around):
            with _client(tmp_path, monkeypatch) as client:
                response = client.post("/search", json=SEARCH_BODY)
    assert response.status_code == 200
    data = response.json()["data"]
    assert "search_id" in data
    mid = data["midpoint"]
    expected_lon, expected_lat = midpoint(120.212, 30.291, 120.165, 30.260)
    assert abs(mid["longitude"] - expected_lon) < 1e-9
    assert abs(mid["latitude"] - expected_lat) < 1e-9
    names = [item["name"] for item in data["pois"]]
    assert names == ["近的店", "中间的店", "远的店"]
    assert all("distance_to_midpoint_m" in item for item in data["pois"])
    assert data["pois"][0]["distance_to_midpoint_m"] < data["pois"][1]["distance_to_midpoint_m"]
    computed = haversine_m(expected_lon, expected_lat, expected_lon + 0.001, expected_lat)
    assert abs(data["pois"][0]["distance_to_midpoint_m"] - round(computed)) <= 1


def test_search_missing_fields_returns_422(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.post("/search", json={"city_a": "杭州"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_search_missing_key_returns_502(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch, search_mock=False, amap_api_key="") as client:
        response = client.post("/search", json=SEARCH_BODY)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "SEARCH_NOT_CONFIGURED"


def test_search_mock_returns_demo_pois(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch, search_mock=True, amap_api_key="") as client:
        response = client.post("/search", json=SEARCH_BODY)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["pois"]) == 3
    assert data["pois"][0]["distance_to_midpoint_m"] <= data["pois"][-1]["distance_to_midpoint_m"]
    saved = list((tmp_path / "search").iterdir())
    assert saved


def test_search_no_candidates_returns_422(tmp_path, monkeypatch) -> None:
    calls = {"around": 0}

    async def fake_geocode(city: str, address: str):
        return (120.2, 30.2)

    async def fake_around(*_args, **_kwargs):
        calls["around"] += 1
        return []

    with patch("services.search.geocode_address", new=fake_geocode):
        with patch("services.search.search_around", new=fake_around):
            with _client(tmp_path, monkeypatch) as client:
                response = client.post("/search", json=SEARCH_BODY)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_CANDIDATES"
    assert calls["around"] == 2


def test_search_ambiguous_geocode() -> None:
    geocodes = [
        {
            "formatted_address": "浙江省杭州市上城区杭州东站",
            "city": "杭州市",
            "level": "兴趣点",
            "location": "120.212,30.291",
            "district": "上城区",
        },
        {
            "formatted_address": "浙江省杭州市上城区杭州东站西广场",
            "city": "杭州市",
            "level": "兴趣点",
            "location": "120.208,30.288",
            "district": "上城区",
        },
    ]
    try:
        pick_geocode(geocodes, "杭州", "杭州东站")
    except AppError as exc:
        assert exc.code == "LOCATION_AMBIGUOUS"
        assert exc.status_code == 422
    else:
        raise AssertionError("expected AppError")


def test_search_does_not_merge_300m_neighbors() -> None:
    geocodes = [
        {
            "formatted_address": "浙江省杭州市西湖区龙翔桥地铁站",
            "city": "杭州市",
            "level": "公交地铁站点",
            "location": "120.1650,30.2600",
            "district": "西湖区",
        },
        {
            "formatted_address": "浙江省杭州市西湖区龙翔桥",
            "city": "杭州市",
            "level": "兴趣点",
            "location": "120.1665,30.2612",
            "district": "西湖区",
        },
    ]
    distance = haversine_m(120.1650, 30.2600, 120.1665, 30.2612)
    assert distance < 300
    assert distance > 30
    try:
        pick_geocode(geocodes, "杭州", "西湖龙翔桥地铁站")
    except AppError as exc:
        assert exc.code == "LOCATION_AMBIGUOUS"
    else:
        raise AssertionError("expected AppError")
