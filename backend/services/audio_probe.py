"""Probe real audio container, codec, and duration. This is inspection, not transcoding."""

from __future__ import annotations

import json
import logging
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from exceptions import AppError

logger = logging.getLogger("meetup")

ALLOWED_CONTAINERS = {"webm", "matroska", "ogg"}
ALLOWED_CODECS = {"opus"}
STAGE = "upload"

FfprobeRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass
class ProbeResult:
    containers: list[str]
    codec: str
    duration_s: float
    duration_source: str


def _parse_float(value: Any) -> float | None:
    if value is None or value in ("", "N/A", "n/a", "nan"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number) or number < 0:
        return None
    return number


def run_ffprobe(
    args: list[str],
    timeout_s: float,
    runner: FfprobeRunner | None = None,
) -> dict[str, Any]:
    execute = runner or subprocess.run
    if runner is None:
        binary = args[0] if args else ""
        if shutil.which(binary) is None and not Path(binary).is_file():
            raise AppError(
                502,
                "PROBE_UNAVAILABLE",
                "服务器缺少音频探测工具 ffprobe，请先安装 FFmpeg。探测只读取容器、编码和时长，不会转码。macOS 可执行：brew install ffmpeg",
                STAGE,
            )
    try:
        completed = execute(
            args,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AppError(
            502,
            "PROBE_UNAVAILABLE",
            "服务器缺少音频探测工具 ffprobe，请先安装 FFmpeg。探测只读取容器、编码和时长，不会转码。macOS 可执行：brew install ffmpeg",
            STAGE,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            504,
            "PROBE_TIMEOUT",
            "音频探测超时，请稍后重试。",
            STAGE,
        ) from exc

    if completed.returncode != 0:
        logger.info("stage=upload probe_failed returncode=%s", completed.returncode)
        raise AppError(
            415,
            "UNSUPPORTED_MEDIA_TYPE",
            "不支持的录音格式，请使用浏览器录制的 WebM/Opus 或 Ogg/Opus。",
            STAGE,
        )
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AppError(
            415,
            "UNSUPPORTED_MEDIA_TYPE",
            "不支持的录音格式，请使用浏览器录制的 WebM/Opus 或 Ogg/Opus。",
            STAGE,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            415,
            "UNSUPPORTED_MEDIA_TYPE",
            "不支持的录音格式，请使用浏览器录制的 WebM/Opus 或 Ogg/Opus。",
            STAGE,
        )
    return payload


def _audio_stream(payload: dict[str, Any]) -> dict[str, Any] | None:
    for stream in payload.get("streams") or []:
        if stream.get("codec_type") == "audio":
            return stream
    return None


def _containers_of(payload: dict[str, Any]) -> list[str]:
    raw = str((payload.get("format") or {}).get("format_name") or "")
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _duration_from_metadata(payload: dict[str, Any]) -> tuple[float | None, str]:
    stream = _audio_stream(payload) or {}
    stream_duration = _parse_float(stream.get("duration"))
    if stream_duration is not None:
        return stream_duration, "stream"
    format_duration = _parse_float((payload.get("format") or {}).get("duration"))
    if format_duration is not None:
        return format_duration, "format"
    tags = stream.get("tags") or {}
    tagged = _parse_float(tags.get("DURATION") or tags.get("duration"))
    if tagged is not None:
        return tagged, "stream_tags"
    return None, ""


def _duration_from_packets(payload: dict[str, Any]) -> float | None:
    ends: list[float] = []
    starts: list[float] = []
    for packet in payload.get("packets") or []:
        pts = _parse_float(packet.get("pts_time"))
        if pts is None:
            continue
        starts.append(pts)
        packet_duration = _parse_float(packet.get("duration_time")) or 0.0
        ends.append(pts + packet_duration)
    if not starts:
        return None
    return max(0.0, max(ends) - min(starts))


def probe_audio(
    path: Path,
    ffprobe_bin: str = "ffprobe",
    timeout_s: float = 10.0,
    runner: FfprobeRunner | None = None,
) -> ProbeResult:
    metadata = run_ffprobe(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout_s=timeout_s,
        runner=runner,
    )
    containers = _containers_of(metadata)
    if not any(name in ALLOWED_CONTAINERS for name in containers):
        raise AppError(
            415,
            "UNSUPPORTED_MEDIA_TYPE",
            "不支持的录音格式，请使用浏览器录制的 WebM/Opus 或 Ogg/Opus。",
            STAGE,
        )
    stream = _audio_stream(metadata)
    codec = str((stream or {}).get("codec_name") or "").lower()
    if codec not in ALLOWED_CODECS:
        raise AppError(
            415,
            "UNSUPPORTED_MEDIA_TYPE",
            "不支持的录音格式，请使用浏览器录制的 WebM/Opus 或 Ogg/Opus。",
            STAGE,
        )

    duration_s, source = _duration_from_metadata(metadata)
    if duration_s is None:
        # Browser WebM often omits Duration. Use packet timestamps instead of rejecting.
        packets = run_ffprobe(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-print_format",
                "json",
                "-select_streams",
                "a:0",
                "-show_entries",
                "packet=pts_time,duration_time",
                str(path),
            ],
            timeout_s=timeout_s,
            runner=runner,
        )
        duration_s = _duration_from_packets(packets)
        source = "packets"

    if duration_s is None:
        raise AppError(
            422,
            "INVALID_DURATION",
            "无法从音频流或时间戳读取录音时长，请重新录制。缺少 Duration 元数据本身不是错误。",
            STAGE,
        )

    logger.info(
        "stage=upload probe_ok containers=%s codec=%s duration_s=%.3f source=%s",
        ",".join(containers),
        codec,
        duration_s,
        source,
    )
    return ProbeResult(
        containers=containers,
        codec=codec,
        duration_s=duration_s,
        duration_source=source,
    )
