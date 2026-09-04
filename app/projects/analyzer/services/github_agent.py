import json
import re
from typing import Dict, List

import requests
from flask import current_app

from app.projects.analyzer.services.ai_client import AIClientError, complete_chat

GITHUB_API = "https://api.github.com"


def _complete_prompt(prompt: str) -> str:
    try:
        return complete_chat(prompt)
    except AIClientError as exc:
        raise ValueError(f"AI client request failed: {exc}") from exc


def fetch_github_code(url: str, max_lines: int = 300) -> str:
    match = re.search(r"github\.com/([^/]+)/([^/]+)", url.strip())
    if not match:
        return ""

    owner, repo = match.group(1), match.group(2).rstrip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]

    headers = {"Accept": "application/vnd.github.v3+json"}
    try:
        github_token = current_app.config.get("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"token {github_token}"
    except Exception:
        pass

    code_exts = (
        ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cpp", ".c",
        ".go", ".rb", ".php", ".rs", ".swift", ".kt", ".scala", ".cs"
    )
    ignore_parts = {
        "test", "tests", "__pycache__", "node_modules", "dist", "build",
        ".venv", "venv", "migrations", "vendor", ".git"
    }

    code_lines = []

    # 1. Try Git Trees API (recursive across all branches/folders)
    try:
        tree_resp = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/HEAD?recursive=1",
            headers=headers,
            timeout=15,
        )
        if tree_resp.status_code == 200:
            tree_data = tree_resp.json().get("tree", [])
            candidates = [
                item for item in tree_data
                if item.get("type") == "blob"
                and any(item.get("path", "").endswith(ext) for ext in code_exts)
                and not any(p in ignore_parts for p in item.get("path", "").split("/"))
            ]

            def sort_key(item):
                p = item.get("path", "").lower()
                if p.startswith(("src/", "app/", "lib/", "core/", "pkg/")):
                    return 0
                if "/" not in p:
                    return 1
                return 2

            candidates.sort(key=sort_key)

            for item in candidates[:8]:
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{item['path']}"
                file_resp = requests.get(raw_url, headers=headers, timeout=15)
                if file_resp.status_code == 200:
                    lines = [l for l in file_resp.text.splitlines() if l.strip()]
                    code_lines.append(f"# File: {item['path']}")
                    code_lines.extend(lines[:80])
                    if len(code_lines) >= max_lines:
                        break

            if code_lines:
                return "\n".join(code_lines[:max_lines])
    except Exception:
        pass

    # 2. Fallback: Root /contents listing
    try:
        response = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/contents", headers=headers, timeout=20)
        if response.status_code == 200:
            files = response.json()
            if isinstance(files, list):
                for item in files:
                    if item.get("type") == "file" and any(item.get("name", "").endswith(ext) for ext in code_exts):
                        raw_url = item.get("download_url") or f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{item.get('name')}"
                        file_response = requests.get(raw_url, headers=headers, timeout=15)
                        if file_response.status_code == 200:
                            lines = [l for l in file_response.text.splitlines() if l.strip()]
                            code_lines.append(f"# File: {item.get('name')}")
                            code_lines.extend(lines[:80])
                            if len(code_lines) >= max_lines:
                                break
                if code_lines:
                    return "\n".join(code_lines[:max_lines])

                # 3. Fallback: If no code at root, check README.md
                for item in files:
                    if item.get("name", "").lower() == "readme.md":
                        raw_url = item.get("download_url") or f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{item.get('name')}"
                        r_resp = requests.get(raw_url, headers=headers, timeout=15)
                        if r_resp.status_code == 200:
                            return r_resp.text[:2000]
    except Exception:
        pass

    return "\n".join(code_lines[:max_lines])


def generate_questions_from_github(github_urls: List[str], num_questions: int = 10) -> Dict:
    all_code = []
    for url in github_urls:
        code = fetch_github_code(url)
        if code:
            all_code.append(code)
    code_text = "\n\n".join(all_code)
    if not code_text:
        return {"questions": [], "summary": "No code found."}

    prompt = f"""
You are a technical interviewer. Read the following code (from multiple GitHub repos, max 200 lines per file). 
Generate {num_questions} insightful technical basic questions about the codebase and the code not be asking like from this file
 you have used this so what it works in your project,
 make question common like suppose a person use for loop then you should not be asking like why you used for loop in you app.py
  instead of this ask like when we use for loop (general question), and a short summary (like a resume) of the codebase's purpose and technologies.
  don't use like in this project, in this file, or in this repo make it general question.
  and ask only basic questions

Respond ONLY with a JSON object with keys:
- questions: array of strings
- summary: string

---
CODE:
{code_text}
---
"""
    response_text = _complete_prompt(prompt)
    try:
        json_str = re.search(r"\{[\s\S]*\}", response_text).group(0)
        data = json.loads(json_str)
        return {"questions": data.get("questions", []), "summary": data.get("summary", "")}
    except Exception as exc:
        return {"questions": [], "summary": f"Error: {exc}"}


def generate_questions_from_jd(jd: str, num_questions: int = 10) -> Dict:
    prompt = f"""
You are a technical interviewer. Read the following Job Description.
Generate {num_questions} insightful technical basic questions based on the requirements and skills mentioned in the JD.
Make the questions general (e.g., "When would you use a microservices architecture?" instead of "Why did you use microservices in this project?").
Also provide a short summary of the key technical requirements from the JD.

Respond ONLY with a JSON object with keys:
- questions: array of strings
- summary: string

---
Job Description:
{jd}
---
"""
    response_text = _complete_prompt(prompt)
    try:
        json_str = re.search(r"\{[\s\S]*\}", response_text).group(0)
        data = json.loads(json_str)
        return {"questions": data.get("questions", []), "summary": data.get("summary", "")}
    except Exception as exc:
        return {"questions": [], "summary": f"Error: {exc}"}


def extract_experience_section(resume_text: str) -> str:
    prompt = f"""
You are a resume parser. Extract the "Experience" or "Work History" section from the following resume text.
Return ONLY the text content of that section. If not found, return an empty string.

Resume Text:
{resume_text}
"""
    try:
        return _complete_prompt(prompt).strip()
    except Exception:
        return ""


def generate_questions_from_experience(experience_text: str, num_questions: int = 5) -> Dict:
    if not experience_text:
        return {"questions": [], "summary": ""}

    prompt = f"""
You are a technical interviewer. Read the following Experience section from a candidate's resume.
Generate {num_questions} insightful technical questions based on the projects and roles described.
Focus on the technologies and challenges mentioned.
Make the questions specific to their experience but framed as technical inquiries (e.g., "You mentioned working with Kafka. How did you handle message ordering?").
Also provide a short summary of their key experience highlights.

Respond ONLY with a JSON object with keys:
- questions: array of strings (questions should be easy to answer - just a basic level of questions in simple words)
- summary: string

---
Experience Section:
{experience_text}
---
"""
    response_text = _complete_prompt(prompt)
    try:
        json_str = re.search(r"\{[\s\S]*\}", response_text).group(0)
        data = json.loads(json_str)
        return {"questions": data.get("questions", []), "summary": data.get("summary", "")}
    except Exception as exc:
        return {"questions": [], "summary": f"Error: {exc}"}


def extract_project_section(resume_text: str) -> str:
    prompt = f"""
You are a resume parser. Extract the "Projects" section from the following resume text.
Return ONLY the text content of that section. If not found, return an empty string.

Resume Text:
{resume_text}
"""
    try:
        return _complete_prompt(prompt).strip()
    except Exception:
        return ""


def generate_questions_from_projects(project_text: str) -> List[Dict]:
    if not project_text:
        return []

    prompt = f"""
You are a technical interviewer. Read the following Projects section from a candidate's resume.
Identify each distinct project. For each project:
1. Extract the Project Name.
2. Write a short summary of the project.
3. Generate 3-5 basic, easy-to-answer technical questions specific to that project.

Respond ONLY with a JSON array of objects, where each object has:
- project_name: string
- summary: string
- questions: array of strings

---
Projects Section:
{project_text}
---
"""
    response_text = _complete_prompt(prompt)
    try:
        json_str = re.search(r"\[[\s\S]*\]", response_text).group(0)
        return json.loads(json_str)
    except Exception:
        return []
