import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from api.asr import router as asr_router
from api.extract import router as extract_router
from api.health import router as health_router
from api.search import router as search_router
from api.upload import router as upload_router
from config import settings
from exceptions import AppError
from services.storage import cleanup_expired

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("meetup")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    removed = cleanup_expired()
    logger.info("stage=startup cleanup_expired count=%s", removed)
    yield


app = FastAPI(
    title="语音约碰面地点",
    description="已提供健康检查、录音上传、语音识别、地址提取和找店。播报尚未实现。",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next: Callable) -> Response:
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


def _request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.info("stage=%s code=%s", exc.stage, exc.code)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "request_id": _request_id_of(request),
            "error": {
                "code": exc.code,
                "message": exc.message,
                "stage": exc.stage,
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.info("request validation failed stage=request")
    return JSONResponse(
        status_code=422,
        content={
            "request_id": _request_id_of(request),
            "error": {
                "code": "INVALID_REQUEST",
                "message": "请求缺少必要字段或字段类型不正确，请检查后重试。",
                "stage": "request",
            },
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    if exc.status_code == 404:
        code = "NOT_FOUND"
        message = "请求的资源不存在。"
        stage = "app"
    else:
        code = "HTTP_ERROR"
        message = str(exc.detail)
        stage = "app"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "request_id": _request_id_of(request),
            "error": {"code": code, "message": message, "stage": stage},
        },
    )


app.include_router(health_router)
app.include_router(upload_router)
app.include_router(asr_router)
app.include_router(extract_router)
app.include_router(search_router)
