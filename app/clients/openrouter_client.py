from typing import Optional

import requests
from flask import current_app


class OpenRouterError(Exception):
    pass


def complete_chat(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    api_key = current_app.config.get("OPENROUTER_API_KEY")
    if not api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not configured.")

    payload = {
        "model": model or current_app.config.get("OPENROUTER_MODEL", "amazon/nova-2-lite-v1:free"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens or current_app.config.get("AI_MAX_TOKENS", 2048),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": current_app.config.get("OPENROUTER_HTTP_REFERER", "http://localhost"),
        "X-Title": current_app.config.get("OPENROUTER_TITLE", "Main Dashboard"),
    }
    response = requests.post(
        current_app.config.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions"),
        headers=headers,
        json=payload,
        timeout=90,
    )
    if response.status_code != 200:
        raise OpenRouterError(f"OpenRouter request failed ({response.status_code}): {response.text}")

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise OpenRouterError("OpenRouter response missing completion text.") from exc
