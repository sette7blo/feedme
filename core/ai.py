"""Shared AI provider configuration helpers."""
from dataclasses import dataclass

from openai import OpenAI

from core import config

DEFAULT_BASE_URL = "https://api.ppq.ai/v1"
DEFAULT_TEXT_MODEL = "gpt-4o-mini"
DEFAULT_IMAGE_MODEL = "dall-e-3"
DEFAULT_VISION_MODEL = "gpt-4o"


@dataclass(frozen=True)
class AIConfig:
    api_key: str
    base_url: str
    text_model: str
    image_model: str
    vision_model: str


def get_ai_config() -> AIConfig:
    return AIConfig(
        api_key=config.get("PPQ_API_KEY", ""),
        base_url=config.get("PPQ_BASE_URL", DEFAULT_BASE_URL),
        text_model=config.get("PPQ_MODEL", DEFAULT_TEXT_MODEL),
        image_model=config.get("PPQ_IMAGE_MODEL", DEFAULT_IMAGE_MODEL),
        vision_model=config.get("PPQ_VISION_MODEL", DEFAULT_VISION_MODEL),
    )


def require_api_key(ai_config: AIConfig | None = None) -> AIConfig:
    ai_config = ai_config or get_ai_config()
    if not ai_config.api_key:
        raise ValueError("PPQ_API_KEY not configured. Add it in Settings.")
    return ai_config


def client(ai_config: AIConfig | None = None, *, timeout: float | None = None) -> OpenAI:
    ai_config = require_api_key(ai_config)
    kwargs = {"api_key": ai_config.api_key, "base_url": ai_config.base_url}
    if timeout is not None:
        kwargs["timeout"] = timeout
    return OpenAI(**kwargs)
