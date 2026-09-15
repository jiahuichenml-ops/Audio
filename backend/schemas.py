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


class ExtractRequest(BaseModel):
    text: str = Field(min_length=1, examples=["我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。"])
    city: str = Field(min_length=1, examples=["杭州"])


class ExtractData(BaseModel):
    city_a: str = Field(examples=["杭州"])
    address_a: str = Field(examples=["杭州东站"])
    city_b: str = Field(examples=["杭州"])
    address_b: str = Field(examples=["西湖龙翔桥地铁站"])
    category: str = Field(examples=["咖啡店"])


class SearchRequest(BaseModel):
    city_a: str = Field(min_length=1, examples=["杭州"])
    address_a: str = Field(min_length=1, examples=["杭州东站"])
    city_b: str = Field(min_length=1, examples=["杭州"])
    address_b: str = Field(min_length=1, examples=["西湖龙翔桥地铁站"])
    category: str = Field(min_length=1, examples=["咖啡店"])


class MidpointData(BaseModel):
    longitude: float
    latitude: float


class PoiData(BaseModel):
    name: str
    address: str
    distance_to_midpoint_m: float


class SearchData(BaseModel):
    search_id: str
    midpoint: MidpointData
    pois: list[PoiData]


class ErrorBody(BaseModel):
    code: str
    message: str
    stage: str


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorBody
