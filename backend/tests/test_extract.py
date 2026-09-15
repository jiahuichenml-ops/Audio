from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from exceptions import AppError
from main import app
from services.extract import ModelExtract, parse_model_payload, validate_extract


def _client(monkeypatch, **settings_overrides) -> TestClient:
    from config import settings

    monkeypatch.setattr(settings, "extract_mock", False)
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    for key, value in settings_overrides.items():
        monkeypatch.setattr(settings, key, value)
    return TestClient(app)


def test_extract_returns_five_fields(monkeypatch) -> None:
    with patch("api.extract.extract_from_text", new=AsyncMock(return_value={
        "city_a": "杭州",
        "address_a": "杭州东站",
        "city_b": "杭州",
        "address_b": "西湖龙翔桥地铁站",
        "category": "咖啡店",
    })):
        with _client(monkeypatch) as client:
            response = client.post(
                "/extract",
                json={
                    "text": "我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。",
                    "city": "杭州",
                },
            )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {
        "city_a": "杭州",
        "address_a": "杭州东站",
        "city_b": "杭州",
        "address_b": "西湖龙翔桥地铁站",
        "category": "咖啡店",
    }
    assert "party_count" not in data


def test_extract_missing_fields_returns_422(monkeypatch) -> None:
    with _client(monkeypatch) as client:
        response = client.post("/extract", json={"text": "你好"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_extract_missing_key_returns_502(monkeypatch) -> None:
    with _client(monkeypatch, extract_mock=False, deepseek_api_key="") as client:
        response = client.post(
            "/extract",
            json={
                "text": "我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。",
                "city": "杭州",
            },
        )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EXTRACT_NOT_CONFIGURED"


def test_extract_mock_returns_demo_fields(monkeypatch) -> None:
    with _client(monkeypatch, extract_mock=True, deepseek_api_key="") as client:
        response = client.post(
            "/extract",
            json={"text": "任意文本", "city": "杭州"},
        )
    assert response.status_code == 200
    assert response.json()["data"]["address_a"] == "杭州东站"


def test_extract_invalid_json_is_model_error_not_user_error() -> None:
    try:
        parse_model_payload("not-json")
    except AppError as exc:
        assert exc.status_code == 502
        assert exc.code == "EXTRACT_INVALID_RESPONSE"
        assert exc.stage == "extract"
    else:
        raise AssertionError("expected AppError")


def test_extract_rejects_missing_address() -> None:
    model = ModelExtract(
        city_a="杭州",
        address_a=None,
        city_b="杭州",
        address_b="西湖龙翔桥地铁站",
        category="咖啡店",
        party_count=2,
        incomplete_reason="缺少具体地址",
    )
    try:
        validate_extract(model)
    except AppError as exc:
        assert exc.status_code == 422
        assert exc.code == "ADDRESS_MISSING"
    else:
        raise AssertionError("expected AppError")


def test_extract_rejects_home_as_address() -> None:
    model = ModelExtract(
        city_a="杭州",
        address_a="我家",
        city_b="杭州",
        address_b="西湖龙翔桥地铁站",
        category="咖啡店",
        party_count=2,
        incomplete_reason="地址含糊",
    )
    try:
        validate_extract(model)
    except AppError as exc:
        assert exc.code == "ADDRESS_MISSING"
    else:
        raise AssertionError("expected AppError")


def test_extract_rejects_party_count() -> None:
    model = ModelExtract(
        city_a="杭州",
        address_a="杭州东站",
        city_b="杭州",
        address_b="西湖龙翔桥地铁站",
        category="咖啡店",
        party_count=3,
        incomplete_reason="人数不是两人",
    )
    try:
        validate_extract(model)
    except AppError as exc:
        assert exc.code == "PARTY_COUNT"
    else:
        raise AssertionError("expected AppError")


def test_extract_rejects_cross_city() -> None:
    model = ModelExtract(
        city_a="杭州",
        address_a="杭州东站",
        city_b="上海",
        address_b="上海虹桥站",
        category="咖啡店",
        party_count=2,
        incomplete_reason=None,
    )
    try:
        validate_extract(model)
    except AppError as exc:
        assert exc.code == "CROSS_CITY"
    else:
        raise AssertionError("expected AppError")


def test_extract_normalizes_category_and_city() -> None:
    model = ModelExtract(
        city_a="杭州市",
        address_a="杭州东站",
        city_b="杭州",
        address_b="西湖龙翔桥地铁站",
        category="喝咖啡",
        party_count=2,
        incomplete_reason=None,
    )
    data = validate_extract(model)
    assert data["category"] == "咖啡店"
    assert data["city_a"] == "杭州市"
    assert data["city_b"] == "杭州"
