"""Temporary audio and search records. Paths are never returned to clients."""

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


def search_root() -> Path:
    path = settings.storage_dir / "search"
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


def new_search_id() -> str:
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


def load_audio_record(audio_id: str, stage: str = "upload") -> dict[str, Any]:
    meta_path = _record_dir(audio_id) / "meta.json"
    if not meta_path.is_file():
        raise AppError(
            404,
            "AUDIO_NOT_FOUND",
            "录音编号不存在或已过期，请重新上传。",
            stage,
        )
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        created_at = datetime.fromisoformat(meta["created_at"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise AppError(
            404,
            "AUDIO_NOT_FOUND",
            "录音编号不存在或已过期，请重新上传。",
            stage,
        ) from exc
    if is_expired(created_at):
        raise AppError(
            404,
            "AUDIO_NOT_FOUND",
            "录音编号不存在或已过期，请重新上传。",
            stage,
        )
    stored_name = meta.get("stored_name")
    stored_path = _record_dir(audio_id) / stored_name if stored_name else None
    if stored_path is None or not stored_path.is_file():
        raise AppError(
            404,
            "AUDIO_NOT_FOUND",
            "录音编号不存在或已过期，请重新上传。",
            stage,
        )
    meta["path"] = stored_path
    meta["created_at_dt"] = created_at
    return meta


def save_search_record(search_id: str, extra_meta: dict[str, Any]) -> Path:
    destination = search_root() / search_id
    destination.mkdir(parents=True, exist_ok=True)
    meta = {
        "search_id": search_id,
        "created_at": _now().isoformat(),
        **extra_meta,
    }
    path = destination / "meta.json"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_search_record(search_id: str, stage: str = "search") -> dict[str, Any]:
    meta_path = search_root() / search_id / "meta.json"
    if not meta_path.is_file():
        raise AppError(
            404,
            "SEARCH_NOT_FOUND",
            "查询编号不存在或已过期，请重新搜索。",
            stage,
        )
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        created_at = datetime.fromisoformat(meta["created_at"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise AppError(
            404,
            "SEARCH_NOT_FOUND",
            "查询编号不存在或已过期，请重新搜索。",
            stage,
        ) from exc
    if is_expired(created_at):
        raise AppError(
            404,
            "SEARCH_NOT_FOUND",
            "查询编号不存在或已过期，请重新搜索。",
            stage,
        )
    meta["created_at_dt"] = created_at
    return meta


def _cleanup_root(root: Path, current: datetime) -> int:
    if not root.exists():
        return 0
    removed = 0
    for record_dir in root.iterdir():
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


def cleanup_expired(now: datetime | None = None) -> int:
    current = now or _now()
    return _cleanup_root(audio_root(), current) + _cleanup_root(search_root(), current)
