"""Shared AI provider configuration helpers."""
from dataclasses import dataclass

from openai import OpenAI

from core import config

DEFAULT_BASE_URL = "https://api.ppq.ai/v1"
DEFAULT_TEXT_MODEL = "gpt-4o-mini"
DEFAULT_IMAGE_MODEL = "dall-e-3"
DEFAULT_VISION_MODEL = "gpt-4o"
DEFAULT_VISION_DETAIL = "low"
DEFAULT_GENERATE_IMAGES = True


@dataclass(frozen=True)
class AIConfig:
    api_key: str
    base_url: str
    text_model: str
    image_model: str
    vision_model: str
    vision_detail: str
    generate_images: bool


def _bool_setting(key: str, default: bool) -> bool:
    raw = config.get(key, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _vision_detail() -> str:
    detail = config.get("AI_VISION_DETAIL", DEFAULT_VISION_DETAIL).strip().lower()
    return detail if detail in {"low", "auto", "high"} else DEFAULT_VISION_DETAIL


def get_ai_config() -> AIConfig:
    return AIConfig(
        api_key=config.get("PPQ_API_KEY", ""),
        base_url=config.get("PPQ_BASE_URL", DEFAULT_BASE_URL),
        text_model=config.get("PPQ_MODEL", DEFAULT_TEXT_MODEL),
        image_model=config.get("PPQ_IMAGE_MODEL", DEFAULT_IMAGE_MODEL),
        vision_model=config.get("PPQ_VISION_MODEL", DEFAULT_VISION_MODEL),
        vision_detail=_vision_detail(),
        generate_images=_bool_setting("GENERATE_IMAGES_BY_DEFAULT", DEFAULT_GENERATE_IMAGES),
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
