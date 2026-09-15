import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from exceptions import AppError
from main import app
from services.audio_probe import ProbeResult


def _seed_audio(tmp_path, audio_id: str = "11111111-1111-1111-1111-111111111111", expired: bool = False) -> None:
    folder = tmp_path / "audio" / audio_id
    folder.mkdir(parents=True)
    (folder / "recording.webm").write_bytes(b"fake-webm")
    created = datetime.now(timezone.utc) - (
        timedelta(hours=25) if expired else timedelta(minutes=1)
    )
    meta = {
        "audio_id": audio_id,
        "created_at": created.isoformat(),
        "stored_name": "recording.webm",
        "codec": "opus",
        "containers": ["webm"],
    }
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def _client(tmp_path, monkeypatch) -> TestClient:
    from config import settings

    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(settings, "bailian_api_key", "sk-test")
    return TestClient(app)


def test_asr_returns_text(tmp_path, monkeypatch) -> None:
    audio_id = "22222222-2222-2222-2222-222222222222"
    _seed_audio(tmp_path, audio_id)
    probe = ProbeResult(["webm"], "opus", 3.2, "packets")
    with patch("api.asr.probe_audio", return_value=probe):
        with patch(
            "api.asr.recognize_data_uri",
            new=AsyncMock(return_value="我在杭州东站，朋友在西湖龙翔桥地铁站。"),
        ):
            with _client(tmp_path, monkeypatch) as client:
                response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["text"] == "我在杭州东站，朋友在西湖龙翔桥地铁站。"
    assert "request_id" in body


def test_asr_missing_id_returns_422(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.post("/asr", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_asr_unknown_id_returns_404(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.post("/asr", json={"audio_id": "not-found"})
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "AUDIO_NOT_FOUND"
    assert body["error"]["stage"] == "asr"


def test_asr_expired_id_returns_404(tmp_path, monkeypatch) -> None:
    audio_id = "33333333-3333-3333-3333-333333333333"
    _seed_audio(tmp_path, audio_id, expired=True)
    with _client(tmp_path, monkeypatch) as client:
        response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AUDIO_NOT_FOUND"


def test_asr_empty_transcript_returns_422(tmp_path, monkeypatch) -> None:
    audio_id = "44444444-4444-4444-4444-444444444444"
    _seed_audio(tmp_path, audio_id)
    probe = ProbeResult(["webm"], "opus", 2.0, "packets")
    with patch("api.asr.probe_audio", return_value=probe):
        with patch(
            "api.asr.recognize_data_uri",
            new=AsyncMock(
                side_effect=AppError(
                    422,
                    "ASR_EMPTY",
                    "没有识别出有效文字，请重新录制后再试。",
                    "asr",
                )
            ),
        ):
            with _client(tmp_path, monkeypatch) as client:
                response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ASR_EMPTY"


def test_asr_timeout_returns_504(tmp_path, monkeypatch) -> None:
    audio_id = "55555555-5555-5555-5555-555555555555"
    _seed_audio(tmp_path, audio_id)
    probe = ProbeResult(["webm"], "opus", 2.0, "packets")
    with patch("api.asr.probe_audio", return_value=probe):
        with patch(
            "api.asr.recognize_data_uri",
            new=AsyncMock(
                side_effect=AppError(
                    504,
                    "ASR_TIMEOUT",
                    "语音识别超时，请稍后重试。",
                    "asr",
                )
            ),
        ):
            with _client(tmp_path, monkeypatch) as client:
                response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "ASR_TIMEOUT"


def test_asr_missing_key_returns_502(tmp_path, monkeypatch) -> None:
    from config import settings

    audio_id = "66666666-6666-6666-6666-666666666666"
    _seed_audio(tmp_path, audio_id)
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(settings, "bailian_api_key", "")
    monkeypatch.setattr(settings, "asr_mock", False)
    probe = ProbeResult(["webm"], "opus", 2.0, "packets")
    with patch("api.asr.probe_audio", return_value=probe):
        with TestClient(app) as client:
            response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ASR_NOT_CONFIGURED"


def test_asr_mock_returns_fixed_text_without_key(tmp_path, monkeypatch) -> None:
    from config import settings

    audio_id = "77777777-7777-7777-7777-777777777777"
    _seed_audio(tmp_path, audio_id)
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(settings, "bailian_api_key", "")
    monkeypatch.setattr(settings, "asr_mock", True)
    monkeypatch.setattr(
        settings,
        "asr_mock_text",
        "我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。",
    )
    probe = ProbeResult(["webm"], "opus", 2.0, "packets")
    with patch("api.asr.probe_audio", return_value=probe):
        with patch("api.asr.recognize_data_uri", new=AsyncMock()) as recognize:
            with TestClient(app) as client:
                response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 200
    assert response.json()["data"]["text"] == (
        "我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。"
    )
    recognize.assert_not_called()
