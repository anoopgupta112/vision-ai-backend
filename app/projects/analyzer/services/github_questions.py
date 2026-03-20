import os
import re

from app.projects.analyzer.services.github_agent import (
    extract_experience_section,
    extract_project_section,
    generate_questions_from_experience,
    generate_questions_from_github,
    generate_questions_from_jd,
    generate_questions_from_projects,
)
from app.projects.analyzer.services.match_agent import evaluate_resume_against_jd
from app.projects.analyzer.services.ocr_engine import extract_text_from_pdf


def process_uploaded_pdfs(pdf_files: list, jd: str, save_dir: str) -> list:
    results = []

    for pdf in pdf_files:
        base_name = os.path.basename(pdf.filename)
        save_path = os.path.join(save_dir, base_name)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        pdf.save(save_path)

        resume_text, links = extract_text_from_pdf(save_path)
        match_report = evaluate_resume_against_jd(jd, resume_text)
        github_questions = []

        if links:
            github_links = [link["uri"] for link in links if isinstance(link, dict) and "uri" in link and re.match(r"https://github.com/", link["uri"])]
            repo_links = []
            for github_url in github_links:
                if re.match(r"https://github.com/[^/]+/[^/]+", github_url):
                    repo_links.append(github_url)

            unique_repos = list(set(repo_links))
            for github_url in unique_repos:
                qdata = generate_questions_from_github([github_url], 10)
                if qdata.get("summary") == "No code found.":
                    continue
                github_questions.append(
                    {
                        "repo": github_url,
                        "questions": qdata.get("questions", []),
                        "summary": qdata.get("summary", ""),
                        "source": "github",
                    }
                )

        if not github_questions:
            jd_qdata = generate_questions_from_jd(jd, 10)
            if jd_qdata.get("questions"):
                github_questions.append(
                    {
                        "repo": "Job Description",
                        "questions": jd_qdata.get("questions", []),
                        "summary": jd_qdata.get("summary", ""),
                        "source": "jd",
                    }
                )

        experience_text = extract_experience_section(resume_text)
        if experience_text:
            exp_qdata = generate_questions_from_experience(experience_text, 5)
            if exp_qdata.get("questions"):
                github_questions.append(
                    {
                        "repo": "Experience",
                        "questions": exp_qdata.get("questions", []),
                        "summary": exp_qdata.get("summary", ""),
                        "source": "experience",
                    }
                )

        project_text = extract_project_section(resume_text)
        if project_text:
            projects_data = generate_questions_from_projects(project_text)
            for project in projects_data:
                github_questions.append(
                    {
                        "repo": project.get("project_name", "Project"),
                        "questions": project.get("questions", []),
                        "summary": project.get("summary", ""),
                        "source": "project",
                    }
                )

        results.append(
            {
                "pdf_path": base_name,
                "match_report": match_report,
                "links": links,
                "github_questions": github_questions,
                "resume_text": resume_text,
            }
        )

    return results
