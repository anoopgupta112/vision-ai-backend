import json
import re
from typing import Any, Dict

from app.projects.analyzer.services.ai_client import AIClientError, complete_chat


def evaluate_resume_against_jd(jd: str, resume_text: str):
    prompt = f"""
You are a professional HR evaluator. Your task is to strictly match the candidate's resume against a Job Description.

If the Job Description is too short, missing, or meaningless (less than 10 valid words), set `percent_match` to 0, and provide negatives explaining the issue.

Respond ONLY with a JSON object using the schema:

- percent_match: integer (0-100)
- positive: array of objects with:
    - description: string
    - keywords: array of strings
- negative: array of objects with:
    - description: string
    - keywords: array of strings
- description: overall summary of fit

Job Description:
{jd}

Resume Text:
{resume_text}
"""
    try:
        response_text = complete_chat(prompt)
    except AIClientError as exc:
        raise ValueError(f"AI client request failed: {exc}") from exc
    return extract_json_from_text(response_text)


def extract_json_from_text(text: str) -> Dict[str, Any]:
    try:
        json_str = re.search(r"\{[\s\S]*\}", text).group(0)
    except AttributeError as exc:
        raise ValueError("No JSON block found.") from exc

    open_curly = json_str.count("{")
    close_curly = json_str.count("}")
    if open_curly > close_curly:
        json_str += "}" * (open_curly - close_curly)
    open_square = json_str.count("[")
    close_square = json_str.count("]")
    if open_square > close_square:
        json_str += "]" * (open_square - close_square)

    try:
        raw = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError("Failed to parse corrected JSON.") from exc

    percent = raw.get("percent_match", 0)
    if isinstance(percent, str):
        percent = re.sub(r"[^\d]", "", percent)
    try:
        percent = int(percent)
    except Exception:
        percent = 0

    return {
        "percent_match": percent,
        "positive": raw.get("positive", []),
        "negative": raw.get("negative", []),
        "description": raw.get("description", "N/A"),
    }
