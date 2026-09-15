from fastapi import APIRouter, Request

from schemas import SuccessResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=SuccessResponse,
    summary="Health check",
)
def health(request: Request) -> dict:
    """Return service status. Does not call external providers or require API keys."""
    return {
        "request_id": request.state.request_id,
        "data": {"status": "ok"},
    }
