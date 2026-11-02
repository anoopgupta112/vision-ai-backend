import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

from flask import current_app, has_app_context

logger = logging.getLogger(__name__)


class RedditAIClientError(Exception):
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
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    """
    Executes chat completion with Vertex AI as the primary provider,
    falling back to Gemini, Groq, or OpenRouter if available.
    """
    errors = []

    # 1. Primary: Vertex AI
    if _get_config("VERTEX_API_KEY"):
        try:
            from app.clients import vertex_client
            return vertex_client.complete_chat(
                prompt=prompt,
                model=model or _get_config("VERTEX_MODEL"),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning("Vertex AI completion failed: %s. Trying fallback...", exc)
            errors.append(f"Vertex AI: {exc}")

    # 2. Gemini (Key rotation support via app.clients.gemini_client)
    has_gemini = _get_config("GEMINI_API_KEY") or _get_config("GEMINI_API_KEY_1")
    if has_gemini:
        try:
            from app.clients import gemini_client
            return gemini_client.complete_chat(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning("Gemini completion failed: %s. Trying fallback...", exc)
            errors.append(f"Gemini: {exc}")

    # 3. Fallback: Groq
    if _get_config("GROQ_API_KEY"):
        try:
            from app.clients import groq_client
            return groq_client.complete_chat(
                prompt=prompt,
                model=model or _get_config("GROQ_MODEL"),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning("Groq completion failed: %s", exc)
            errors.append(f"Groq: {exc}")

    # 4. Fallback: OpenRouter
    if _get_config("OPENROUTER_API_KEY"):
        try:
            from app.clients import openrouter_client
            return openrouter_client.complete_chat(
                prompt=prompt,
                model=model or _get_config("OPENROUTER_MODEL"),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning("OpenRouter completion failed: %s", exc)
            errors.append(f"OpenRouter: {exc}")

    if errors:
        raise RedditAIClientError(f"All configured AI providers failed: {' | '.join(errors)}")

    raise RedditAIClientError(
        "No AI provider configured. Please provide VERTEX_API_KEY, GEMINI_API_KEY, or GROQ_API_KEY."
    )


def complete_json(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Ensures prompt requests JSON, completes chat, and parses the returned JSON string safely.
    Uses native JSON mode when Vertex AI is configured.
    """
    if _get_config("VERTEX_API_KEY"):
        try:
            from app.clients import vertex_client
            return vertex_client.complete_json(
                prompt=prompt,
                model=model or _get_config("VERTEX_MODEL"),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning("Vertex complete_json failed: %s. Trying general parsing fallback...", exc)

    if "JSON" not in prompt:
        prompt += "\n\nRespond ONLY with a valid JSON object. Do not include markdown code block backticks."

    raw_response = complete_chat(
        prompt=prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    clean_text = raw_response.strip()
    # Strip markdown ```json ... ``` code blocks if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
    if match:
        clean_text = match.group(1).strip()

    try:
        value = json.loads(clean_text)
        if not isinstance(value, dict):
            raise RedditAIClientError("AI response must be a JSON object.")
        return value
    except json.JSONDecodeError:
        # Fallback regex extraction of outermost braces
        brace_match = re.search(r"(\{[\s\S]*\})", clean_text)
        if brace_match:
            try:
                return json.loads(brace_match.group(1))
            except Exception:
                pass
        raise RedditAIClientError(f"Could not parse valid JSON from AI response: {clean_text[:200]}")


def get_current_provider() -> str:
    if _get_config("VERTEX_API_KEY"):
        return "Vertex AI"
    if _get_config("GEMINI_API_KEY") or _get_config("GEMINI_API_KEY_1"):
        return "Gemini"
    if _get_config("GROQ_API_KEY"):
        return "Groq"
    if _get_config("OPENROUTER_API_KEY"):
        return "OpenRouter"
    return "None"
