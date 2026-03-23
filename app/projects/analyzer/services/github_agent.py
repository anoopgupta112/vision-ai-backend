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


def fetch_github_code(url: str, max_lines: int = 200) -> str:
    match = re.match(r"https://github.com/([^/]+)/([^/]+)(/|$)", url)
    if not match:
        return ""

    owner, repo = match.group(1), match.group(2)
    headers = {"Accept": "application/vnd.github.v3+json"}
    github_token = current_app.config.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    response = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/contents", headers=headers, timeout=30)
    if response.status_code != 200:
        return ""

    files = response.json()
    code = []
    for item in files:
        if item["type"] != "file":
            continue
        if not item["name"].endswith((".py", ".js", ".ts", ".java", ".cpp", ".c", ".go", ".rb", ".php", ".rs", ".swift", ".kt", ".scala", ".cs")):
            continue
        raw_url = item["download_url"]
        file_response = requests.get(raw_url, headers=headers, timeout=30)
        if file_response.status_code != 200:
            continue
        lines = file_response.text.splitlines()
        code.extend(lines[: max_lines - len(code)])
        if len(code) >= max_lines:
            break
    return "\n".join(code)


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
