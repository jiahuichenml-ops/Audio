"""Read local settings. Empty API keys must not block /health."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Project defaults (confirmed): local ports and CORS.
    backend_host: str = "127.0.0.1"
    backend_port: int = 8003
    cors_origins: str = "http://localhost:5175,http://127.0.0.1:5175"
    public_base_url: str = "http://localhost:8003"

    # Keys are filled by the operator. Empty values are valid for health checks.
    bailian_api_key: str = ""
    deepseek_api_key: str = ""
    amap_api_key: str = ""

    # Official DashScope Beijing endpoints (not inferred from a shared prefix).
    # ASR: https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference
    asr_model: str = "qwen3-asr-flash"
    asr_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    # TTS: https://help.aliyun.com/zh/model-studio/qwen-tts-api
    tts_model: str = "qwen3-tts-flash"
    tts_url: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    )
    tts_voice: str = "Cherry"
    tts_language_type: str = "Chinese"

    # Official DeepSeek OpenAI-compatible chat completions.
    # https://api-docs.deepseek.com/  current model id is deepseek-flash;
    # deepseek-v4-flash remains accepted. This project keeps the confirmed name.
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_url: str = "https://api.deepseek.com/chat/completions"

    # Official Amap Web service endpoints from the agreed spec.
    amap_geocode_url: str = "https://restapi.amap.com/v3/geocode/geo"
    amap_place_around_url: str = "https://restapi.amap.com/v3/place/around"

    storage_dir: Path = Field(default=_BACKEND_DIR / "storage")
    temp_ttl_hours: int = 24
    ffprobe_path: str = "ffprobe"
    ffprobe_timeout_s: float = 10.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
