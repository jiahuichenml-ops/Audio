"""Shared request and response shapes. Health uses the success envelope."""

from typing import Any

from pydantic import BaseModel, Field


class SuccessResponse(BaseModel):
    request_id: str
    data: dict[str, Any]


class HealthData(BaseModel):
    status: str = Field(examples=["ok"])


class UploadData(BaseModel):
    audio_id: str = Field(examples=["b6c1f2a0-4d3e-4c8a-9f11-2a7c0e8d91aa"])


class AsrRequest(BaseModel):
    audio_id: str = Field(min_length=1, examples=["b6c1f2a0-4d3e-4c8a-9f11-2a7c0e8d91aa"])


class AsrData(BaseModel):
    text: str = Field(examples=["我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。"])


class ErrorBody(BaseModel):
    code: str
    message: str
    stage: str


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorBody
