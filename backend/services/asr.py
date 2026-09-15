"""Call Bailian Beijing qwen3-asr-flash. Never log API keys or audio Base64."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from config import settings
from exceptions import AppError

logger = logging.getLogger("meetup")
STAGE = "asr"


def mime_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".ogg":
        return "audio/ogg"
    return "audio/webm"


def encode_audio_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    if len(encoded.encode("ascii")) > settings.asr_max_base64_bytes:
        raise AppError(
            413,
            "BASE64_TOO_LARGE",
            "编码后的音频过大，无法提交识别。",
            STAGE,
        )
    mime = mime_type_for_path(path)
    return f"data:{mime};base64,{encoded}"


def _extract_text(payload: object) -> str:
    if not isinstance(payload, dict):
        raise AppError(
            502,
            "ASR_INVALID_RESPONSE",
            "语音识别服务返回无法解析的结果，请稍后重试。",
            STAGE,
        )
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices, list):
        raise AppError(
            502,
            "ASR_INVALID_RESPONSE",
            "语音识别服务没有返回识别文字，请稍后重试。",
            STAGE,
        )
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise AppError(
            422,
            "ASR_EMPTY",
            "没有识别出有效文字，请重新录制后再试。",
            STAGE,
        )
    return content.strip()


def mock_transcript() -> str:
    text = settings.asr_mock_text.strip()
    if not text:
        raise AppError(
            422,
            "ASR_EMPTY",
            "没有识别出有效文字，请重新录制后再试。",
            STAGE,
        )
    logger.info("stage=asr mock=1 text_chars=%s", len(text))
    return text


async def recognize_data_uri(data_uri: str) -> str:
    api_key = settings.bailian_api_key.strip()
    if not api_key:
        raise AppError(
            502,
            "ASR_NOT_CONFIGURED",
            "未配置百炼密钥，无法识别语音。请在 backend/.env 填写 BAILIAN_API_KEY 后重启服务。",
            STAGE,
        )

    timeout = httpx.Timeout(
        connect=5.0,
        read=settings.asr_timeout_s,
        write=10.0,
        pool=5.0,
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.asr_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data_uri},
                    }
                ],
            }
        ],
        "stream": False,
        "asr_options": {"enable_itn": False},
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                settings.asr_url,
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as exc:
        logger.info("stage=asr timeout")
        raise AppError(
            504,
            "ASR_TIMEOUT",
            "语音识别超时，请稍后重试。",
            STAGE,
        ) from exc
    except httpx.HTTPError as exc:
        logger.info("stage=asr http_error type=%s", type(exc).__name__)
        raise AppError(
            502,
            "ASR_UPSTREAM",
            "语音识别服务暂时不可用，请稍后重试。",
            STAGE,
        ) from exc

    if response.status_code >= 500:
        logger.info("stage=asr upstream_status=%s", response.status_code)
        raise AppError(
            502,
            "ASR_UPSTREAM",
            "语音识别服务暂时不可用，请稍后重试。",
            STAGE,
        )
    if response.status_code in {401, 403}:
        logger.info("stage=asr upstream_status=%s", response.status_code)
        raise AppError(
            502,
            "ASR_UNAUTHORIZED",
            "百炼密钥无效或没有语音识别权限，请检查后重试。",
            STAGE,
        )
    if response.status_code >= 400:
        logger.info("stage=asr upstream_status=%s", response.status_code)
        raise AppError(
            502,
            "ASR_UPSTREAM",
            "语音识别失败，请稍后重试。",
            STAGE,
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise AppError(
            502,
            "ASR_INVALID_RESPONSE",
            "语音识别服务返回无法解析的结果，请稍后重试。",
            STAGE,
        ) from exc
    return _extract_text(body)
