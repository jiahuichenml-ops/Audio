from fastapi.testclient import TestClient

from main import app


def test_health_returns_ok_without_api_keys() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "request_id" in body
    assert isinstance(body["request_id"], str)
    assert body["request_id"]
    assert body["data"] == {"status": "ok"}
