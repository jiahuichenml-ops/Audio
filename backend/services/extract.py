"""Call DeepSeek to extract two addresses. Never log API keys or raw prompts with secrets."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from config import settings
from exceptions import AppError
from services.geo import same_city

logger = logging.getLogger("meetup")
STAGE = "extract"
VAGUE_ADDRESSES = {"我家", "你家", "他家", "公司", "单位", "学校", "这边", "那里", "附近"}
CATEGORY_ALIASES = {"喝咖啡": "咖啡店", "咖啡": "咖啡店", "咖啡馆": "咖啡店", "cafe": "咖啡店"}


class ModelExtract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    city_a: str | None = None
    address_a: str | None = None
    city_b: str | None = None
    address_b: str | None = None
    category: str | None = None
    party_count: int | None = None
    incomplete_reason: str | None = None


class ExtractResult(BaseModel):
    city_a: str = Field(min_length=1)
    address_a: str = Field(min_length=1)
    city_b: str = Field(min_length=1)
    address_b: str = Field(min_length=1)
    category: str = Field(min_length=1)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_category(value: str | None) -> str:
    text = _clean(value)
    if not text:
        return "咖啡店"
    return CATEGORY_ALIASES.get(text.lower(), CATEGORY_ALIASES.get(text, text))


def _is_vague(address: str | None) -> bool:
    text = _clean(address)
    if not text:
        return True
    if text in VAGUE_ADDRESSES:
        return True
    return any(text.startswith(token) for token in ("我家", "你家", "公司", "单位"))


def load_extract_prompt() -> str:
    path = settings.extract_prompt_path
    return path.read_text(encoding="utf-8")


def mock_extract() -> dict[str, str]:
    logger.info("stage=extract mock=1")
    return {
        "city_a": "杭州",
        "address_a": "杭州东站",
        "city_b": "杭州",
        "address_b": "西湖龙翔桥地铁站",
        "category": "咖啡店",
    }


def validate_extract(model: ModelExtract) -> dict[str, str]:
    if model.party_count != 2:
        raise AppError(
            422,
            "PARTY_COUNT",
            "目前只支持同一座城市里的两个人，请重新说明人数和地点。",
            STAGE,
        )
    city_a = _clean(model.city_a)
    city_b = _clean(model.city_b)
    address_a = _clean(model.address_a)
    address_b = _clean(model.address_b)
    if not city_a or not city_b or _is_vague(address_a) or _is_vague(address_b):
        raise AppError(
            422,
            "ADDRESS_MISSING",
            "地点不够具体，请说出两个人的具体地名，不要用「我家」或「公司」这类说法。",
            STAGE,
        )
    if not same_city(city_a, city_b):
        raise AppError(
            422,
            "CROSS_CITY",
            "目前只支持同一座城市内的两人碰面，请改成同城地点后再试。",
            STAGE,
        )
    result = ExtractResult(
        city_a=city_a,
        address_a=address_a or "",
        city_b=city_b,
        address_b=address_b or "",
        category=_normalize_category(model.category),
    )
    return result.model_dump()


def parse_model_payload(raw: str) -> ModelExtract:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError(
            502,
            "EXTRACT_INVALID_RESPONSE",
            "地址提取服务返回了无法解析的结果，请稍后重试。",
            STAGE,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            502,
            "EXTRACT_INVALID_RESPONSE",
            "地址提取服务返回了无法解析的结果，请稍后重试。",
            STAGE,
        )
    try:
        return ModelExtract.model_validate(payload)
    except ValidationError as exc:
        raise AppError(
            502,
            "EXTRACT_INVALID_RESPONSE",
            "地址提取结果格式不符合约定，请稍后重试。",
            STAGE,
        ) from exc


def _extract_content(payload: object) -> str:
    if not isinstance(payload, dict):
        raise AppError(
            502,
            "EXTRACT_INVALID_RESPONSE",
            "地址提取服务返回了无法解析的结果，请稍后重试。",
            STAGE,
        )
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices, list):
        raise AppError(
            502,
            "EXTRACT_INVALID_RESPONSE",
            "地址提取服务没有返回有效内容，请稍后重试。",
            STAGE,
        )
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise AppError(
            502,
            "EXTRACT_INVALID_RESPONSE",
            "地址提取服务没有返回有效内容，请稍后重试。",
            STAGE,
        )
    return content


async def call_deepseek(text: str, page_city: str) -> str:
    api_key = settings.deepseek_api_key.strip()
    if not api_key:
        raise AppError(
            502,
            "EXTRACT_NOT_CONFIGURED",
            "未配置 DeepSeek 密钥，无法提取地点。请在 backend/.env 填写 DEEPSEEK_API_KEY 后重启服务。",
            STAGE,
        )
    timeout = httpx.Timeout(
        connect=5.0,
        read=settings.extract_timeout_s,
        write=10.0,
        pool=5.0,
    )
    user_prompt = f"页面选定城市：{page_city.strip()}\n用户原话：{text.strip()}\n请按系统说明输出 json。"
    payload: dict[str, Any] = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": load_extract_prompt()},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "temperature": 0,
        "max_tokens": 1024,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(settings.deepseek_url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        logger.info("stage=extract timeout")
        raise AppError(
            504,
            "EXTRACT_TIMEOUT",
            "地址提取超时，请稍后重试。",
            STAGE,
        ) from exc
    except httpx.HTTPError as exc:
        logger.info("stage=extract http_error type=%s", type(exc).__name__)
        raise AppError(
            502,
            "EXTRACT_UPSTREAM",
            "地址提取服务暂时不可用，请稍后重试。",
            STAGE,
        ) from exc

    if response.status_code in {401, 403}:
        logger.info("stage=extract upstream_status=%s", response.status_code)
        raise AppError(
            502,
            "EXTRACT_UNAUTHORIZED",
            "DeepSeek 密钥无效或没有访问权限，请检查后重试。",
            STAGE,
        )
    if response.status_code >= 400:
        logger.info("stage=extract upstream_status=%s", response.status_code)
        raise AppError(
            502,
            "EXTRACT_UPSTREAM",
            "地址提取失败，请稍后重试。",
            STAGE,
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise AppError(
            502,
            "EXTRACT_INVALID_RESPONSE",
            "地址提取服务返回了无法解析的结果，请稍后重试。",
            STAGE,
        ) from exc
    return _extract_content(body)


async def extract_from_text(text: str, page_city: str) -> dict[str, str]:
    if settings.extract_mock:
        return mock_extract()
    raw = await call_deepseek(text, page_city)
    model = parse_model_payload(raw)
    return validate_extract(model)
