import logging
import time
from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile

from config import settings
from exceptions import AppError
from schemas import SuccessResponse
from services.audio_probe import probe_audio
from services.storage import new_audio_id, save_audio, write_temp_upload

logger = logging.getLogger("meetup")
router = APIRouter()

MAX_AUDIO_BYTES = 5 * 1024 * 1024
MIN_AUDIO_SECONDS = 1.0
MAX_AUDIO_SECONDS = 60.0


def _suffix_for_filename(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".webm", ".ogg"}:
        return suffix
    return ".webm"


@router.post(
    "/upload",
    response_model=SuccessResponse,
    summary="Upload a recording",
)
async def upload(
    request: Request,
    file: UploadFile = File(..., description="录音文件，字段名必须为 file"),
) -> dict:
    started = time.perf_counter()
    data = await file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise AppError(
            413,
            "FILE_TOO_LARGE",
            "录音文件过大，最大允许 5MB。",
            "upload",
        )
    if not data:
        raise AppError(
            422,
            "EMPTY_FILE",
            "请上传录音文件。",
            "upload",
        )

    suffix = _suffix_for_filename(file.filename)
    temp_path = write_temp_upload(data, suffix)
    try:
        probe = probe_audio(
            temp_path,
            ffprobe_bin=settings.ffprobe_path,
            timeout_s=settings.ffprobe_timeout_s,
        )
        if probe.duration_s < MIN_AUDIO_SECONDS:
            raise AppError(
                422,
                "DURATION_TOO_SHORT",
                "录音时长过短，请按住至少 1 秒后重试。",
                "upload",
            )
        if probe.duration_s > MAX_AUDIO_SECONDS:
            raise AppError(
                422,
                "DURATION_TOO_LONG",
                "录音时长超过 60 秒，请缩短后重试。",
                "upload",
            )
        audio_id = new_audio_id()
        save_audio(
            audio_id,
            temp_path,
            suffix,
            extra_meta={
                "size_bytes": len(data),
                "duration_s": probe.duration_s,
                "duration_source": probe.duration_source,
                "codec": probe.codec,
                "containers": probe.containers,
                "original_filename": Path(file.filename or "").name,
            },
        )
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "stage=upload ok elapsed_ms=%s audio_id=%s size=%s duration_s=%.3f",
        elapsed_ms,
        audio_id,
        len(data),
        probe.duration_s,
    )
    return {
        "request_id": request.state.request_id,
        "data": {"audio_id": audio_id},
    }
