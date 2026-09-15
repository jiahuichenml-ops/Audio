import logging
import time

from fastapi import APIRouter, Request

from schemas import ExtractRequest, SuccessResponse
from services.extract import extract_from_text

logger = logging.getLogger("meetup")
router = APIRouter()


@router.post(
    "/extract",
    response_model=SuccessResponse,
    summary="Extract two addresses and a meetup category",
)
async def extract(request: Request, body: ExtractRequest) -> dict:
    started = time.perf_counter()
    data = await extract_from_text(body.text, body.city)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info("stage=extract ok elapsed_ms=%s", elapsed_ms)
    return {
        "request_id": request.state.request_id,
        "data": data,
    }
