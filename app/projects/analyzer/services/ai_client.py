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


def complete_chat(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
) -> str:
    # 1. Primary: Groq API
    if _get_config("GROQ_API_KEY"):
        try:
            from app.clients import groq_client

            return groq_client.complete_chat(prompt, model, temperature, max_tokens)
        except Exception as exc:
            if not (_get_config("GEMINI_API_KEY") or _get_config("GEMINI_API_KEY_1") or _get_config("OPENROUTER_API_KEY")):
                raise AIClientError(f"Groq client error: {exc}") from exc

    # 2. Fallback: Gemini
    if _get_config("GEMINI_API_KEY") or _get_config("GEMINI_API_KEY_1"):
        try:
            from app.clients import gemini_client

            return gemini_client.complete_chat(prompt, model, temperature, max_tokens)
        except Exception as exc:
            if not _get_config("OPENROUTER_API_KEY"):
                raise AIClientError(f"Gemini client error: {exc}") from exc

    # 3. Fallback: OpenRouter
    if _get_config("OPENROUTER_API_KEY"):
        try:
            from app.clients import openrouter_client

            return openrouter_client.complete_chat(prompt, model, temperature, max_tokens)
        except Exception as exc:
            raise AIClientError(f"OpenRouter client error: {exc}") from exc

    raise AIClientError("No active AI provider configured (GROQ_API_KEY is required).")


def get_current_provider() -> str:
    if _get_config("GROQ_API_KEY"):
        return "Groq"
    if _get_config("GEMINI_API_KEY") or _get_config("GEMINI_API_KEY_1"):
        return "Gemini"
    return "OpenRouter"
