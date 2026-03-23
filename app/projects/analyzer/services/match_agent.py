import json
import re
from typing import Any, Dict

from app.projects.analyzer.services.ai_client import AIClientError, complete_chat


def evaluate_resume_against_jd(jd: str, resume_text: str):
    prompt = _analysis_prompt(jd, resume_text)
    try:
        response_text = complete_chat(prompt, temperature=0.0, max_tokens=4096)
        return extract_json_from_text(response_text)
    except AIClientError as exc:
        return _fallback_match_report("AI client request failed: %s" % exc)
    except ValueError:
        pass

    try:
        correction_prompt = _json_correction_prompt(jd, resume_text, response_text)
        corrected_response = complete_chat(correction_prompt, temperature=0.0, max_tokens=2048)
        return extract_json_from_text(corrected_response)
    except AIClientError as exc:
        return _fallback_match_report("AI client request failed after retry: %s" % exc)
    except ValueError as exc:
        return _fallback_match_report(str(exc))


def _analysis_prompt(jd: str, resume_text: str) -> str:
    return f"""
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

Keep the response concise:
- maximum 4 positive items
- maximum 4 negative items
- each description should be one sentence
- each keywords list should contain at most 5 short keywords

Job Description:
{jd}

Resume Text:
{resume_text}
"""


def _json_correction_prompt(jd: str, resume_text: str, previous_response: str) -> str:
    return f"""
You previously answered a resume-vs-JD analysis request, but the response was not valid JSON.

Return ONLY a valid JSON object with this exact schema:
{{
  "percent_match": 0,
  "positive": [{{"description": "string", "keywords": ["string"]}}],
  "negative": [{{"description": "string", "keywords": ["string"]}}],
  "description": "string"
}}

Do not use markdown fences.
Do not add commentary before or after the JSON.

Job Description:
{jd}

Resume Text:
{resume_text}

Previous invalid response:
{previous_response}
"""


def _fallback_match_report(reason: str) -> Dict[str, Any]:
    return {
        "percent_match": 0,
        "positive": [],
        "negative": [
            {
                "description": "Automated JD analysis was unavailable for this file.",
                "keywords": ["analysis_unavailable"],
            },
            {
                "description": reason[:300],
                "keywords": ["ai_response_error"],
            },
        ],
        "description": "Unable to analyze automatically right now. Please retry.",
    }


def extract_json_from_text(text: str) -> Dict[str, Any]:
    json_str = _extract_candidate_json(text)
    raw = _load_json_with_repairs(json_str)

    percent = raw.get("percent_match", 0)
    if isinstance(percent, str):
        percent = re.sub(r"[^\d]", "", percent)
    try:
        percent = int(percent)
    except Exception:
        percent = 0

    return {
        "percent_match": percent,
        "positive": _normalize_findings(raw.get("positive", [])),
        "negative": _normalize_findings(raw.get("negative", [])),
        "description": raw.get("description", "N/A"),
    }


def _extract_candidate_json(text: str) -> str:
    fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    if fenced_match:
        return fenced_match.group(1)

    first_curly = text.find("{")
    if first_curly == -1:
        raise ValueError("No JSON block found.")

    depth = 0
    in_string = False
    escaped = False
    start = None

    for index in range(first_curly, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    return text[start : index + 1]

    candidate = text[first_curly:]
    if candidate.strip():
        return candidate
    raise ValueError("No JSON block found.")


def _load_json_with_repairs(json_str: str) -> Dict[str, Any]:
    candidates = [
        json_str.strip(),
        re.sub(r"^```(?:json)?\s*|\s*```$", "", json_str.strip(), flags=re.IGNORECASE),
        re.sub(r",(\s*[}\]])", r"\1", json_str.strip()),
    ]

    balanced = _balance_json_like_text(candidates[0])
    if balanced not in candidates:
        candidates.append(balanced)
        candidates.append(re.sub(r",(\s*[}\]])", r"\1", balanced))

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise ValueError("Failed to parse corrected JSON.")


def _balance_json_like_text(json_str: str) -> str:
    open_curly = json_str.count("{")
    close_curly = json_str.count("}")
    if open_curly > close_curly:
        json_str += "}" * (open_curly - close_curly)
    open_square = json_str.count("[")
    close_square = json_str.count("]")
    if open_square > close_square:
        json_str += "]" * (open_square - close_square)
    return json_str


def _normalize_findings(items: Any) -> list[Dict[str, Any]]:
    normalized = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            normalized.append({"description": item, "keywords": []})
            continue
        if isinstance(item, dict):
            description = str(item.get("description", "")).strip()
            keywords = item.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = [str(keywords)]
            normalized.append(
                {
                    "description": description,
                    "keywords": [str(keyword) for keyword in keywords if str(keyword).strip()],
                }
            )
    return normalized
