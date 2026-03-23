"""
automation.custom_feature
~~~~~~~~~~~~~~~~~~~~~~~~~
Turns a plain-language feature description into a structured feature manifest
candidate, using Gemini when available or a simple fallback when not.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional


DISCOVERY_SKILL_FILE = Path(__file__).resolve().parent / "discovery_skill.json"

_PROMPT_TEMPLATE = """\
You are a senior software engineer helping an automation system plan a new feature.

## Project Context
Project: {project_name}
Summary: {project_summary}

## Example Feature Templates (for style/format reference)
{feature_templates_json}

## Task
The user has described a feature they want to build:

\"\"\"{description}\"\"\"

Backend repo: {backend_repo}
Frontend repo: {frontend_repo}

Generate a structured feature manifest as a JSON object with EXACTLY these fields:
{{
  "id": "kebab-case-id-for-this-feature",
  "title": "Human-readable feature title",
  "priority": <integer 1-100, lower = higher priority>,
  "category": "one of: core_platform, data_features, ai_support, ux_polish, payments",
  "summary": "1-2 sentence description",
  "acceptance_criteria": ["criterion 1", "criterion 2", "criterion 3"],
  "api_contract": ["METHOD /path/to/endpoint description", "..."],
  "branches": {{
    "backend": "agent/<slug>-backend",
    "frontend": "agent/<slug>-frontend"
  }},
  "implementation_notes": "Key technical implementation details, which files to change, design decisions"
}}

Rules:
- id must be unique kebab-case, derived from the feature title
- acceptance_criteria: 3-6 specific, testable criteria
- api_contract: list all new or modified API endpoints
- branches: use "agent/<slug>-backend" and "agent/<slug>-frontend" format
- If the feature is backend-only, still include both branch fields
- Return ONLY the JSON object, no markdown fences, no explanation
"""


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "custom-feature"


def _load_skill(skill_file: Optional[Path] = None) -> dict:
    skill_file = skill_file or DISCOVERY_SKILL_FILE
    if skill_file.exists():
        return json.loads(skill_file.read_text())
    return {"project_name": "", "project_summary": "", "feature_templates": []}


def _fallback_candidate(description: str, backend_repo: str, frontend_repo: str) -> Dict[str, Any]:
    """Minimal candidate when Gemini is unavailable."""
    slug = _slugify(description[:60])
    title = description.strip().rstrip(".").capitalize()[:80]
    return {
        "id": slug,
        "title": title,
        "priority": 50,
        "category": "core_platform",
        "summary": description.strip(),
        "acceptance_criteria": [
            f"Feature '{title}' is implemented and visible to users",
            "Feature works on both backend and frontend without errors",
            "Existing functionality is not broken",
        ],
        "api_contract": ["(API contract to be determined during implementation)"],
        "branches": {
            "backend": f"agent/{slug}-backend",
            "frontend": f"agent/{slug}-frontend",
        },
        "implementation_notes": description.strip(),
        "backend_repo": backend_repo,
        "frontend_repo": frontend_repo,
        "status": "suggested",
        "_source": "custom_fallback",
    }


def expand_feature_description(
    description: str,
    backend_repo: str,
    frontend_repo: str,
    project_name: str = "",
    skill_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Expand a plain-language description into a structured feature candidate dict.

    Uses Gemini when GEMINI_API_KEY is configured; falls back to a minimal
    candidate otherwise.  Always returns a dict compatible with the feature
    manifest schema.
    """
    description = description.strip()
    if not description:
        raise ValueError("Feature description must not be empty.")

    skill = _load_skill(skill_file)
    effective_project = project_name or skill.get("project_name", "")

    # Limit templates to avoid huge prompts
    templates_sample = skill.get("feature_templates", [])[:5]

    try:
        from flask import current_app
        from app.clients.gemini_client import complete_chat, GeminiError

        if not current_app.config.get("GEMINI_API_KEY"):
            raise GeminiError("GEMINI_API_KEY not set")

        prompt = _PROMPT_TEMPLATE.format(
            project_name=effective_project,
            project_summary=skill.get("project_summary", ""),
            feature_templates_json=json.dumps(templates_sample, indent=2),
            description=description,
            backend_repo=backend_repo,
            frontend_repo=frontend_repo,
        )

        raw = complete_chat(prompt, temperature=0.3, max_tokens=1024)

        # Strip markdown fences if Gemini added them
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"```$", "", raw).strip()

        candidate = json.loads(raw)

    except Exception:
        # Any failure → safe fallback
        return _fallback_candidate(description, backend_repo, frontend_repo)

    # Normalise required fields
    slug = _slugify(candidate.get("id") or candidate.get("title", description[:40]))
    candidate.setdefault("id", slug)
    candidate.setdefault("title", description.strip()[:80])
    candidate.setdefault("priority", 50)
    candidate.setdefault("category", "core_platform")
    candidate.setdefault("summary", description.strip())
    candidate.setdefault("acceptance_criteria", [
        "Feature is implemented and accessible to users",
        "No regressions in existing functionality",
    ])
    candidate.setdefault("api_contract", [])
    candidate.setdefault("branches", {
        "backend": f"agent/{slug}-backend",
        "frontend": f"agent/{slug}-frontend",
    })
    candidate.setdefault("implementation_notes", "")
    candidate["backend_repo"] = backend_repo
    candidate["frontend_repo"] = frontend_repo
    candidate["status"] = "suggested"
    candidate["_source"] = "custom_gemini"

    return candidate
