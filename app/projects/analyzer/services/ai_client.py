import os
from typing import Optional

from flask import current_app, has_app_context


class AIClientError(Exception):
    pass


def _get_config(key: str, default=None):
    if has_app_context():
        val = current_app.config.get(key)
        if val is not None:
            return val
    return os.environ.get(key, default)


def _has_gemini_keys() -> bool:
    if _get_config("GEMINI_API_KEY"):
        return True
    for index in range(1, 7):
        if _get_config("GEMINI_API_KEY_%s" % index):
            return True
    return False


def _prefer_gemini() -> bool:
    return _get_config("USE_GEMINI", False) or _has_gemini_keys()


def complete_chat(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    if _prefer_gemini():
        try:
            from app.clients import gemini_client

            return gemini_client.complete_chat(prompt, model, temperature, max_tokens)
        except Exception as exc:
            if not _get_config("OPENROUTER_API_KEY"):
                raise AIClientError(f"Gemini client error: {exc}") from exc

    try:
        from app.clients import openrouter_client

        return openrouter_client.complete_chat(prompt, model, temperature, max_tokens)
    except Exception as exc:
        raise AIClientError(f"OpenRouter client error: {exc}") from exc


def get_current_provider() -> str:
    return "Gemini" if _prefer_gemini() else "OpenRouter"
