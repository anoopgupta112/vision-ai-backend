import logging
import os
from pathlib import Path
from typing import List, Optional

from flask import current_app, has_app_context

logger = logging.getLogger(__name__)

STATE_FILE_PATH = Path("/tmp/.gemini_last_key_index")


class GeminiError(Exception):
    pass


def _load_key_index() -> int:
    try:
        if STATE_FILE_PATH.exists():
            return int(STATE_FILE_PATH.read_text().strip())
    except Exception:
        pass
    return 0


def _save_key_index(index: int) -> None:
    try:
        STATE_FILE_PATH.write_text(str(index))
    except Exception:
        pass


def _get_config(key: str, default=None):
    if has_app_context():
        val = current_app.config.get(key)
        if val is not None:
            return val
    return os.environ.get(key, default)


def _gemini_key_sort_key(env_name: str) -> tuple:
    if env_name == "GEMINI_API_KEY":
        return (0, 0)
    suffix = env_name.replace("GEMINI_API_KEY_", "")
    try:
        return (1, int(suffix))
    except ValueError:
        return (2, 0)


def _configured_api_keys() -> List[str]:
    keys: List[str] = []

    candidate_names = []
    # Check Flask config
    if has_app_context():
        for k in current_app.config.keys():
            if k == "GEMINI_API_KEY" or (k.startswith("GEMINI_API_KEY_") and k.replace("GEMINI_API_KEY_", "").isdigit()):
                candidate_names.append(k)

    # Check os.environ
    for k in os.environ.keys():
        if k == "GEMINI_API_KEY" or (k.startswith("GEMINI_API_KEY_") and k.replace("GEMINI_API_KEY_", "").isdigit()):
            if k not in candidate_names:
                candidate_names.append(k)

    for env_name in sorted(candidate_names, key=_gemini_key_sort_key):
        val = _get_config(env_name)
        if val and val not in keys:
            keys.append(val)

    return keys


def _candidate_models(requested_model: Optional[str]) -> List[str]:
    models: List[str] = []
    configured = requested_model or _get_config("GEMINI_MODEL", "gemini-2.5-flash")
    for model_name in [
        configured,
        "gemini-2.5-flash",
    ]:
        if model_name and model_name not in models:
            models.append(model_name)
    return models


def should_retry_gemini_error(error_text: str) -> bool:
    return any(marker in error_text for marker in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "quota"))


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
    start_index = _load_key_index()
    max_retries = len(api_keys)
    errors = []

    for model_name in model_names:
        for attempt in range(max_retries):
            current_index = (start_index + attempt) % len(api_keys)
            api_key = api_keys[current_index]

            try:
                genai.configure(api_key=api_key)
                model_instance = genai.GenerativeModel(
                    model_name=model_name,
                    generation_config=generation_config,
                )
                response = model_instance.generate_content(prompt)
                text = getattr(response, "text", "")
                if text:
                    _save_key_index((current_index + 1) % len(api_keys))
                    return text
                errors.append(f"{model_name} [Key #{current_index + 1}]: Empty response")
            except Exception as exc:
                err_msg = str(exc)
                errors.append(f"{model_name} [Key #{current_index + 1}]: {err_msg}")
                if should_retry_gemini_error(err_msg):
                    logger.warning(
                        "Gemini Key #%s rate-limited/exhausted. Rotating to next key...",
                        current_index + 1,
                    )
                    continue
                continue

    if errors:
        raise GeminiError("Gemini API request failed for all configured keys: %s" % " | ".join(errors))
    raise GeminiError("Gemini API request failed for all configured keys.")
