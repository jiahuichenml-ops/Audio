from api.asr import router as asr_router
from api.extract import router as extract_router
from api.health import router as health_router
from api.search import router as search_router
from api.upload import router as upload_router

__all__ = ["health_router", "upload_router", "asr_router", "extract_router", "search_router"]
