import logging
import time

from fastapi import APIRouter, Request

from config import settings
from schemas import AsrRequest, SuccessResponse
from services.asr import encode_audio_data_uri, mock_transcript, recognize_data_uri
from services.audio_probe import probe_audio
from services.storage import load_audio_record

logger = logging.getLogger("meetup")
router = APIRouter()


@router.post(
    "/asr",
    response_model=SuccessResponse,
    summary="Transcribe an uploaded recording",
)
async def asr(request: Request, body: AsrRequest) -> dict:
    started = time.perf_counter()
    record = load_audio_record(body.audio_id, stage="asr")
    path = record["path"]
    probe_audio(
        path,
        ffprobe_bin=settings.ffprobe_path,
        timeout_s=settings.ffprobe_timeout_s,
        stage="asr",
    )
    if settings.asr_mock:
        text = mock_transcript()
    else:
        data_uri = encode_audio_data_uri(path)
        text = await recognize_data_uri(data_uri)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "stage=asr ok elapsed_ms=%s audio_id=%s text_chars=%s",
        elapsed_ms,
        body.audio_id,
        len(text),
    )
    return {
        "request_id": request.state.request_id,
        "data": {"text": text},
    }
