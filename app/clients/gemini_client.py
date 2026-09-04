import os
from typing import List, Optional

from flask import current_app, has_app_context


class GeminiError(Exception):
    pass


def _get_config(key: str, default=None):
    if has_app_context():
        val = current_app.config.get(key)
        if val is not None:
            return val
    return os.environ.get(key, default)


def _configured_api_keys() -> List[str]:
    keys: List[str] = []

    primary = _get_config("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    if primary and primary not in keys:
        keys.append(primary)

    for index in range(1, 7):
        env_name = "GEMINI_API_KEY_%s" % index
        value = _get_config(env_name) or os.environ.get(env_name, "")
        if value and value not in keys:
            keys.append(value)

    return keys


def _candidate_models(requested_model: Optional[str]) -> List[str]:
    models: List[str] = []
    configured = requested_model or _get_config("GEMINI_MODEL", "gemini-2.5-flash")
    for model_name in [
        configured,
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ]:
        if model_name and model_name not in models:
            models.append(model_name)
    return models


def complete_chat(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    api_keys = _configured_api_keys()
    if not api_keys:
        raise GeminiError("No Gemini API keys are configured.")

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise GeminiError("google-generativeai is not installed.") from exc

    generation_config = {
        "temperature": temperature,
        "max_output_tokens": max_tokens or _get_config("AI_MAX_TOKENS", 2048),
    }
    if "Respond ONLY with a JSON object" in prompt or "Return ONLY a valid JSON object" in prompt:
        generation_config["response_mime_type"] = "application/json"
    model_names = _candidate_models(model)
    errors = []

    for model_name in model_names:
        for api_key in api_keys:
            try:
                genai.configure(api_key=api_key)
                model_instance = genai.GenerativeModel(
                    model_name=model_name,
                    generation_config=generation_config,
                )
                response = model_instance.generate_content(prompt)
            except Exception as exc:
                errors.append("%s: %s" % (model_name, str(exc)))
                continue

            if getattr(response, "text", ""):
                return response.text

            errors.append("%s: Gemini response is empty." % model_name)

    if errors:
        raise GeminiError("Gemini API request failed for all configured keys: %s" % " | ".join(errors))
    raise GeminiError("Gemini API request failed for all configured keys.")
