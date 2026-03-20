from typing import Optional

from flask import current_app


class AIClientError(Exception):
    pass


def complete_chat(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    if current_app.config.get("USE_GEMINI", False):
        try:
            from app.clients import gemini_client

            return gemini_client.complete_chat(prompt, model, temperature, max_tokens)
        except Exception as exc:
            raise AIClientError(f"Gemini client error: {exc}") from exc

    try:
        from app.clients import openrouter_client

        return openrouter_client.complete_chat(prompt, model, temperature, max_tokens)
    except Exception as exc:
        raise AIClientError(f"OpenRouter client error: {exc}") from exc


def get_current_provider() -> str:
    return "Gemini" if current_app.config.get("USE_GEMINI", False) else "OpenRouter"
