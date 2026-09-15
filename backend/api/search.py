import logging
import time

from fastapi import APIRouter, Request

from schemas import SearchRequest, SuccessResponse
from services.search import search_meetup

logger = logging.getLogger("meetup")
router = APIRouter()


@router.post(
    "/search",
    response_model=SuccessResponse,
    summary="Geocode two places, search midpoint POIs",
)
async def search(request: Request, body: SearchRequest) -> dict:
    started = time.perf_counter()
    data = await search_meetup(body.model_dump())
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "stage=search ok elapsed_ms=%s search_id=%s poi_count=%s",
        elapsed_ms,
        data["search_id"],
        len(data["pois"]),
    )
    return {
        "request_id": request.state.request_id,
        "data": data,
    }
