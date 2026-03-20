from typing import Optional

from flask import current_app


class GeminiError(Exception):
    pass


def complete_chat(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError("GEMINI_API_KEY is not configured.")

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise GeminiError("google-generativeai is not installed.") from exc

    genai.configure(api_key=api_key)
    generation_config = {
        "temperature": temperature,
        "max_output_tokens": max_tokens or current_app.config.get("AI_MAX_TOKENS", 2048),
    }

    try:
        model_instance = genai.GenerativeModel(
            model_name=model or current_app.config.get("GEMINI_MODEL", "gemini-2.0-flash-exp"),
            generation_config=generation_config,
        )
        response = model_instance.generate_content(prompt)
    except Exception as exc:
        raise GeminiError(f"Gemini API request failed: {exc}") from exc

    if not getattr(response, "text", ""):
        raise GeminiError("Gemini response is empty.")

    return response.text
