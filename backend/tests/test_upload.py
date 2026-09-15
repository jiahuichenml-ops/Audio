from unittest.mock import patch

from fastapi.testclient import TestClient

from exceptions import AppError
from main import app
from services.audio_probe import ProbeResult


def _upload(client: TestClient, content: bytes, filename: str = "meetup-recording.webm"):
    return client.post(
        "/upload",
        files={"file": (filename, content, "audio/webm")},
    )


def test_upload_returns_audio_id(tmp_path, monkeypatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    probe = ProbeResult(["webm"], "opus", 3.2, "packets")
    with patch("api.upload.probe_audio", return_value=probe):
        with TestClient(app) as client:
            response = _upload(client, b"fake-webm-bytes")
    assert response.status_code == 200
    body = response.json()
    assert "request_id" in body
    audio_id = body["data"]["audio_id"]
    assert audio_id
    assert "/" not in audio_id
    assert "storage" not in audio_id
    meta = tmp_path / "audio" / audio_id / "meta.json"
    assert meta.is_file()
    assert '"created_at"' in meta.read_text(encoding="utf-8")


def test_upload_rejects_unsupported_format(tmp_path, monkeypatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    error = AppError(
        415,
        "UNSUPPORTED_MEDIA_TYPE",
        "不支持的录音格式，请使用浏览器录制的 WebM/Opus 或 Ogg/Opus。",
        "upload",
    )
    with patch("api.upload.probe_audio", side_effect=error):
        with TestClient(app) as client:
            response = _upload(client, b"not-audio", filename="note.txt")
    assert response.status_code == 415
    body = response.json()
    assert body["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert body["error"]["stage"] == "upload"


def test_upload_rejects_file_too_large(tmp_path, monkeypatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    oversized = b"a" * (5 * 1024 * 1024 + 1)
    with TestClient(app) as client:
        response = _upload(client, oversized)
    assert response.status_code == 413
    body = response.json()
    assert body["error"]["code"] == "FILE_TOO_LARGE"
    assert body["error"]["stage"] == "upload"


def test_upload_rejects_duration_too_short(tmp_path, monkeypatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    probe = ProbeResult(["webm"], "opus", 0.4, "packets")
    with patch("api.upload.probe_audio", return_value=probe):
        with TestClient(app) as client:
            response = _upload(client, b"short-audio")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "DURATION_TOO_SHORT"
    assert body["error"]["stage"] == "upload"


def test_upload_rejects_empty_file(tmp_path, monkeypatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    with TestClient(app) as client:
        response = _upload(client, b"")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_FILE"


def test_upload_rejects_duration_too_long(tmp_path, monkeypatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    probe = ProbeResult(["webm"], "opus", 61.0, "format")
    with patch("api.upload.probe_audio", return_value=probe):
        with TestClient(app) as client:
            response = _upload(client, b"long-audio")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DURATION_TOO_LONG"
