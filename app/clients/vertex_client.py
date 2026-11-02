import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from flask import current_app, has_app_context

logger = logging.getLogger(__name__)

STATE_FILE_PATH = Path("/tmp/.vertex_last_key_index")


class VertexError(Exception):
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


def _vertex_key_sort_key(env_name: str) -> tuple:
    if env_name == "VERTEX_API_KEY":
        return (0, 0)
    suffix = env_name.replace("VERTEX_API_KEY_", "")
    try:
        return (1, int(suffix))
    except ValueError:
        return (2, 0)


def _configured_api_keys() -> List[str]:
    keys: List[str] = []
    candidate_names = []

    if has_app_context():
        for k in current_app.config.keys():
            if k == "VERTEX_API_KEY" or (
                k.startswith("VERTEX_API_KEY_") and k.replace("VERTEX_API_KEY_", "").isdigit()
            ):
                candidate_names.append(k)

    for k in os.environ.keys():
        if k == "VERTEX_API_KEY" or (
            k.startswith("VERTEX_API_KEY_") and k.replace("VERTEX_API_KEY_", "").isdigit()
        ):
            if k not in candidate_names:
                candidate_names.append(k)

    for env_name in sorted(candidate_names, key=_vertex_key_sort_key):
        val = _get_config(env_name)
        if val and val not in keys:
            keys.append(val)

    return keys


def _candidate_models(requested_model: Optional[str]) -> List[str]:
    models: List[str] = []
    configured = requested_model or _get_config("VERTEX_MODEL", "gemini-2.5-flash")
    for model_name in [
        configured,
        "gemini-2.5-flash",
    ]:
        if model_name and model_name not in models:
            models.append(model_name)
    return models


def should_retry_vertex_error(error_text: str) -> bool:
    return any(
        marker in error_text.lower()
        for marker in (
            "429",
            "rate_limit",
            "resource_exhausted",
            "503",
            "500",
            "502",
            "overloaded",
            "quota",
            "unavailable",
        )
    )


def complete_chat(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    enable_search: bool = False,
    timeout: int = 45,
    is_json: bool = False,
) -> str:
    """
    Executes a chat completion via Google Cloud Vertex AI REST API using an API key.
    """
    api_keys = _configured_api_keys()
    if not api_keys:
        raise VertexError("VERTEX_API_KEY is not configured.")

    project_id = _get_config("VERTEX_PROJECT_ID", "fir-learningwebapp")
    location = _get_config("VERTEX_IMAGE_LOCATION") or _get_config("VERTEX_LOCATION", "us-central1")
    candidate_models = _candidate_models(model)
    max_tokens_val = max_tokens or int(_get_config("AI_MAX_TOKENS", 2048))

    start_index = _load_key_index()
    max_key_attempts = len(api_keys)
    errors = []

    is_json_requested = is_json or (
        not enable_search and any(w in prompt.lower() for w in ("json object", "valid json", "return a json", "respond only with json"))
    )

    for model_name in candidate_models:
        for attempt in range(max_key_attempts):
            current_index = (start_index + attempt) % len(api_keys)
            api_key = api_keys[current_index]

            url = (
                f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}"
                f"/locations/{location}/publishers/google/models/{model_name}:generateContent?key={api_key}"
            )

            generation_config: Dict[str, Any] = {
                "temperature": temperature,
                "maxOutputTokens": max_tokens_val,
            }
            if is_json_requested and not enable_search:
                generation_config["responseMimeType"] = "application/json"

            payload: Dict[str, Any] = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}],
                    }
                ],
                "generationConfig": generation_config,
            }

            if enable_search:
                payload["tools"] = [{"googleSearch": {}}]

            headers = {"Content-Type": "application/json"}

            for key_try in range(3):
                try:
                    response = requests.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=timeout,
                    )

                    if response.status_code == 200:
                        data = response.json()
                        candidates = data.get("candidates") or []
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
                            if text:
                                _save_key_index((current_index + 1) % len(api_keys))
                                return text
                        errors.append(f"{model_name} [Key #{current_index+1}]: Empty candidates response")
                        break
                    elif response.status_code == 400 and "responseMimeType" in generation_config:
                        # Retry without responseMimeType in case schema constraint failed
                        payload["generationConfig"].pop("responseMimeType", None)
                        retry_resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
                        if retry_resp.status_code == 200:
                            data = retry_resp.json()
                            candidates = data.get("candidates") or []
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
                                if text:
                                    _save_key_index((current_index + 1) % len(api_keys))
                                    return text
                        err_body = retry_resp.text[:250]
                        errors.append(
                            f"{model_name} [Key #{current_index+1}] (HTTP {retry_resp.status_code}): {err_body}"
                        )
                        break
                    else:
                        err_body = response.text[:250]
                        errors.append(
                            f"{model_name} [Key #{current_index+1}] (HTTP {response.status_code}): {err_body}"
                        )
                        if should_retry_vertex_error(err_body) and key_try < 2:
                            time.sleep(1)
                            continue
                        break
                except Exception as exc:
                    err_str = str(exc)
                    if key_try < 2 and any(m in err_str.lower() for m in ("connection", "reset", "timeout", "broken", "eof")):
                        time.sleep(1)
                        continue
                    errors.append(f"{model_name} [Key #{current_index+1}]: {err_str}")
                    break

    raise VertexError("Vertex AI request failed across all keys and models: %s" % " | ".join(errors))


def complete_json(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Ensures prompt requests JSON, completes chat via Vertex AI, and parses the returned JSON string safely.
    """
    if "JSON" not in prompt:
        prompt += "\n\nRespond ONLY with a valid JSON object. Do not include markdown code block backticks."

    raw_response = complete_chat(
        prompt=prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        is_json=True,
    )

    clean_text = raw_response.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
    if match:
        clean_text = match.group(1).strip()

    try:
        value = json.loads(clean_text)
        if not isinstance(value, dict):
            raise VertexError("Vertex AI response must be a JSON object.")
        return value
    except json.JSONDecodeError:
        brace_match = re.search(r"(\{[\s\S]*\})", clean_text)
        if brace_match:
            try:
                return json.loads(brace_match.group(1))
            except Exception:
                pass
        raise VertexError(f"Could not parse valid JSON from Vertex AI response: {clean_text[:200]}")
