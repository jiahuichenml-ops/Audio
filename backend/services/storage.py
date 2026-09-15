"""Temporary audio files keyed by audio_id. Paths are never returned to clients."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import settings
from exceptions import AppError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def audio_root() -> Path:
    path = settings.storage_dir / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tmp_root() -> Path:
    path = settings.storage_dir / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _record_dir(audio_id: str) -> Path:
    return audio_root() / audio_id


def new_audio_id() -> str:
    return str(uuid4())


def is_expired(created_at: datetime, now: datetime | None = None) -> bool:
    current = now or _now()
    return current - created_at > timedelta(hours=settings.temp_ttl_hours)


def write_temp_upload(data: bytes, suffix: str) -> Path:
    path = tmp_root() / f"{uuid4()}{suffix}"
    path.write_bytes(data)
    return path


def save_audio(
    audio_id: str,
    source_path: Path,
    suffix: str,
    extra_meta: dict[str, Any],
) -> Path:
    destination = _record_dir(audio_id)
    destination.mkdir(parents=True, exist_ok=True)
    stored_name = f"recording{suffix}"
    stored_path = destination / stored_name
    shutil.move(str(source_path), stored_path)
    meta = {
        "audio_id": audio_id,
        "created_at": _now().isoformat(),
        "stored_name": stored_name,
        **extra_meta,
    }
    (destination / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return stored_path


def load_audio_record(audio_id: str) -> dict[str, Any]:
    meta_path = _record_dir(audio_id) / "meta.json"
    if not meta_path.is_file():
        raise AppError(
            404,
            "AUDIO_NOT_FOUND",
            "录音编号不存在或已过期，请重新上传。",
            "upload",
        )
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        created_at = datetime.fromisoformat(meta["created_at"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise AppError(
            404,
            "AUDIO_NOT_FOUND",
            "录音编号不存在或已过期，请重新上传。",
            "upload",
        ) from exc
    if is_expired(created_at):
        raise AppError(
            404,
            "AUDIO_NOT_FOUND",
            "录音编号不存在或已过期，请重新上传。",
            "upload",
        )
    stored_name = meta.get("stored_name")
    stored_path = _record_dir(audio_id) / stored_name if stored_name else None
    if stored_path is None or not stored_path.is_file():
        raise AppError(
            404,
            "AUDIO_NOT_FOUND",
            "录音编号不存在或已过期，请重新上传。",
            "upload",
        )
    meta["path"] = stored_path
    return meta


def cleanup_expired(now: datetime | None = None) -> int:
    removed = 0
    current = now or _now()
    if not audio_root().exists():
        return 0
    for record_dir in audio_root().iterdir():
        meta_path = record_dir / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            created_at = datetime.fromisoformat(meta["created_at"])
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        if is_expired(created_at, current):
            shutil.rmtree(record_dir, ignore_errors=True)
            removed += 1
    return removed
