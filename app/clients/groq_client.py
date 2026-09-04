import logging
import os
from pathlib import Path
from typing import List, Optional

import requests
from flask import current_app, has_app_context

logger = logging.getLogger(__name__)

STATE_FILE_PATH = Path("/tmp/.groq_last_key_index")


class GroqError(Exception):
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


def _groq_key_sort_key(env_name: str) -> tuple:
    if env_name == "GROQ_API_KEY":
        return (0, 0)
    suffix = env_name.replace("GROQ_API_KEY_", "")
    try:
        return (1, int(suffix))
    except ValueError:
        return (2, 0)


def _configured_api_keys() -> List[str]:
    keys: List[str] = []
    candidate_names = []

    if has_app_context():
        for k in current_app.config.keys():
            if k == "GROQ_API_KEY" or (k.startswith("GROQ_API_KEY_") and k.replace("GROQ_API_KEY_", "").isdigit()):
                candidate_names.append(k)

    for k in os.environ.keys():
        if k == "GROQ_API_KEY" or (k.startswith("GROQ_API_KEY_") and k.replace("GROQ_API_KEY_", "").isdigit()):
            if k not in candidate_names:
                candidate_names.append(k)

    for env_name in sorted(candidate_names, key=_groq_key_sort_key):
        val = _get_config(env_name)
        if val and val not in keys:
            keys.append(val)

    return keys


def _candidate_models(requested_model: Optional[str]) -> List[str]:
    models: List[str] = []
    configured = requested_model or _get_config("GROQ_MODEL", "openai/gpt-oss-120b")
    for model_name in [
        configured,
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.6-27b",
        "qwen/qwen3.8-27b",
        "groq/compound-mini",
        "groq/compound",
    ]:
        if model_name and model_name not in models:
            models.append(model_name)
    return models


def should_retry_groq_error(error_text: str) -> bool:
    return any(marker in error_text.lower() for marker in ("429", "rate_limit", "503", "500", "502", "overloaded", "quota", "400", "bad_request"))


def complete_chat(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
) -> str:
    api_keys = _configured_api_keys()
    if not api_keys:
        raise GroqError("GROQ_API_KEY is not configured.")

    base_url = _get_config("GROQ_BASE_URL", "https://api.groq.com/openai/v1/chat/completions")
    candidate_models = _candidate_models(model)
    max_tokens_val = max_tokens or int(_get_config("AI_MAX_TOKENS", 2048))

    start_index = _load_key_index()
    max_key_attempts = len(api_keys)
    errors = []

    for model_name in candidate_models:
        for attempt in range(max_key_attempts):
            current_index = (start_index + attempt) % len(api_keys)
            api_key = api_keys[current_index]

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens_val,
            }
            if "Respond ONLY with a JSON object" in prompt or "Return ONLY a valid JSON object" in prompt:
                payload["response_format"] = {"type": "json_object"}

            try:
                response = requests.post(
                    base_url,
                    headers=headers,
                    json=payload,
                    timeout=60,
                )
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices") or []
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                        if content:
                            _save_key_index((current_index + 1) % len(api_keys))
                            return content
                    errors.append(f"{model_name} [Key #{current_index+1}]: Empty choices")
                elif response.status_code == 400 and "response_format" in payload:
                    # Retry without response_format if json_object mode caused a 400
                    payload.pop("response_format", None)
                    retry_resp = requests.post(base_url, headers=headers, json=payload, timeout=60)
                    if retry_resp.status_code == 200:
                        data = retry_resp.json()
                        choices = data.get("choices") or []
                        if choices:
                            content = choices[0].get("message", {}).get("content", "")
                            if content:
                                _save_key_index((current_index + 1) % len(api_keys))
                                return content
                    err_body = retry_resp.text[:200]
                    errors.append(f"{model_name} [Key #{current_index+1}] (HTTP {retry_resp.status_code}): {err_body}")
                else:
                    err_body = response.text[:200]
                    errors.append(f"{model_name} [Key #{current_index+1}] (HTTP {response.status_code}): {err_body}")
                    if should_retry_groq_error(err_body):
                        logger.warning("Groq Key #%s error (%s). Trying next key/model...", current_index+1, response.status_code)
                        continue
            except Exception as exc:
                errors.append(f"{model_name} [Key #{current_index+1}]: {str(exc)}")

    raise GroqError("Groq API request failed across all keys and models: %s" % " | ".join(errors))
