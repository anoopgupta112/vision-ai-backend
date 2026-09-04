import os
import re
import operator
import logging
from typing import TypedDict, List, Dict, Any, Annotated, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from langgraph.graph import StateGraph, START, END

from app.projects.analyzer.services.ocr_engine import extract_text_from_pdf
from app.projects.analyzer.services.match_agent import evaluate_resume_against_jd
from app.projects.analyzer.services.github_agent import (
    extract_experience_section,
    extract_project_section,
    generate_questions_from_experience,
    generate_questions_from_projects,
    generate_questions_from_github,
    generate_questions_from_jd,
)
from app.projects.analyzer.services.schemas import (
    ResumeEvaluationOutput,
    TechnicalQuestionSet,
    CandidateAnalysisResult,
)

logger = logging.getLogger(__name__)


class CandidateGraphState(TypedDict):
    pdf_path: str
    file_name: str
    drive_file_id: Optional[str]
    jd: str
    resume_text: str
    links: List[Dict[str, Any]]
    match_report: Optional[Dict[str, Any]]
    question_sets: Annotated[List[Dict[str, Any]], operator.add]
    errors: Annotated[List[str], operator.add]


# Node 1: PDF Extraction (Supports Google Drive in-memory bytes and local files)
def node_extract_pdf(state: CandidateGraphState) -> Dict[str, Any]:
    if state.get("resume_text"):
        return {}
    drive_file_id = state.get("drive_file_id")
    pdf_path = state.get("pdf_path", "")
    try:
        if drive_file_id:
            from app.projects.analyzer.services import google_drive
            pdf_bytes = google_drive.download_file_bytes(drive_file_id)
            resume_text, links = extract_text_from_pdf(pdf_bytes)
            return {
                "resume_text": resume_text or "",
                "links": links or [],
            }
        elif pdf_path and os.path.exists(pdf_path):
            resume_text, links = extract_text_from_pdf(pdf_path)
            return {
                "resume_text": resume_text or "",
                "links": links or [],
            }
        else:
            return {
                "resume_text": "",
                "links": [],
            }
    except Exception as exc:
        logger.error("Failed to extract PDF (drive_id=%s, path=%s): %s", drive_file_id, pdf_path, exc)
        return {
            "resume_text": "",
            "links": [],
            "errors": [f"PDF extraction error: {str(exc)}"],
        }


# Node 2: Resume-to-JD Fit Evaluation
def node_evaluate_fit(state: CandidateGraphState) -> Dict[str, Any]:
    jd = state.get("jd", "")
    resume_text = state.get("resume_text", "")
    try:
        report = evaluate_resume_against_jd(jd, resume_text)
        return {"match_report": report}
    except Exception as exc:
        logger.error("Failed to evaluate match: %s", exc)
        return {
            "match_report": {
                "percent_match": 0,
                "positive": [],
                "negative": [{"description": f"Evaluation error: {str(exc)}", "keywords": []}],
                "description": "Failed to evaluate candidate fit.",
            },
            "errors": [f"Evaluation error: {str(exc)}"],
        }


# Node 3A: GitHub Question Generator (Supports repo and user profile links)
def node_analyze_github(state: CandidateGraphState) -> Dict[str, Any]:
    links = state.get("links", [])
    github_links = []
    for item in links:
        if isinstance(item, dict) and "uri" in item:
            url = item["uri"]
            if "github.com/" in url:
                github_links.append(url)

    qsets = []
    seen = set()
    for gh_url in sorted(set(github_links)):
        if gh_url in seen:
            continue
        seen.add(gh_url)
        try:
            qdata = generate_questions_from_github([gh_url], 10)
            if qdata.get("summary") == "No code found." or not qdata.get("questions"):
                continue
            qsets.append(
                {
                    "repo": gh_url,
                    "questions": qdata.get("questions", []),
                    "summary": qdata.get("summary", ""),
                    "source": "github",
                }
            )
        except Exception as exc:
            logger.warning("Failed analyzing GitHub URL %s: %s", gh_url, exc)

    return {"question_sets": qsets}


# Node 3B: Job Description Question Generator
def node_analyze_jd(state: CandidateGraphState) -> Dict[str, Any]:
    jd = state.get("jd", "")
    qsets = []
    if jd.strip():
        try:
            jd_qdata = generate_questions_from_jd(jd, 10)
            if jd_qdata.get("questions"):
                qsets.append(
                    {
                        "repo": "Job Description",
                        "questions": jd_qdata.get("questions", []),
                        "summary": jd_qdata.get("summary", ""),
                        "source": "jd",
                    }
                )
        except Exception as exc:
            logger.warning("Failed generating JD questions: %s", exc)

    return {"question_sets": qsets}


# Node 4: Parallel Branch for Work Experience & Projects
def node_analyze_experience_projects(state: CandidateGraphState) -> Dict[str, Any]:
    resume_text = state.get("resume_text", "")
    qsets = []

    if resume_text:
        # 1. Experience questions (with fallback to full resume text)
        try:
            experience_text = extract_experience_section(resume_text)
            if not experience_text or len(experience_text.strip()) < 40:
                experience_text = resume_text
            exp_qdata = generate_questions_from_experience(experience_text, 5)
            if exp_qdata.get("questions"):
                qsets.append(
                    {
                        "repo": "Experience",
                        "questions": exp_qdata.get("questions", []),
                        "summary": exp_qdata.get("summary", ""),
                        "source": "experience",
                    }
                )
        except Exception as exc:
            logger.warning("Failed generating experience questions: %s", exc)

        # 2. Projects questions (with fallback to full resume text)
        try:
            project_text = extract_project_section(resume_text)
            if not project_text or len(project_text.strip()) < 40:
                project_text = resume_text
            projects = generate_questions_from_projects(project_text)
            if not projects and project_text != resume_text:
                projects = generate_questions_from_projects(resume_text)

            for project in projects:
                qsets.append(
                    {
                        "repo": project.get("project_name", "Project"),
                        "questions": project.get("questions", []),
                        "summary": project.get("summary", ""),
                        "source": "project",
                    }
                )
        except Exception as exc:
            logger.warning("Failed generating project questions: %s", exc)

    return {"question_sets": qsets}


# Node 5: Synthesize and Validate
def node_synthesize(state: CandidateGraphState) -> Dict[str, Any]:
    return {}


# Build and compile the LangGraph workflow
def create_candidate_analysis_graph():
    workflow = StateGraph(CandidateGraphState)

    # Add all nodes
    workflow.add_node("extract_pdf", node_extract_pdf)
    workflow.add_node("evaluate_fit", node_evaluate_fit)
    workflow.add_node("analyze_github", node_analyze_github)
    workflow.add_node("analyze_jd", node_analyze_jd)
    workflow.add_node("analyze_experience_projects", node_analyze_experience_projects)
    workflow.add_node("synthesize", node_synthesize)

    # Wire edges
    workflow.add_edge(START, "extract_pdf")
    workflow.add_edge("extract_pdf", "evaluate_fit")

    # From evaluate_fit: Fan out in parallel to all question generators
    workflow.add_edge("evaluate_fit", "analyze_github")
    workflow.add_edge("evaluate_fit", "analyze_jd")
    workflow.add_edge("evaluate_fit", "analyze_experience_projects")

    # Fan-in to synthesize
    workflow.add_edge("analyze_github", "synthesize")
    workflow.add_edge("analyze_jd", "synthesize")
    workflow.add_edge("analyze_experience_projects", "synthesize")
    workflow.add_edge("synthesize", END)

    return workflow.compile()


# Global compiled graph instance
analysis_graph = create_candidate_analysis_graph()


def run_candidate_analysis(
    pdf_path: str = "",
    jd: str = "",
    file_name: Optional[str] = None,
    drive_file_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Runs the LangGraph candidate analysis pipeline on a single resume PDF."""
    initial_state: CandidateGraphState = {
        "pdf_path": pdf_path or "",
        "file_name": file_name or (os.path.basename(pdf_path) if pdf_path else "resume.pdf"),
        "drive_file_id": drive_file_id,
        "jd": jd,
        "resume_text": "",
        "links": [],
        "match_report": None,
        "question_sets": [],
        "errors": [],
    }

    final_state = analysis_graph.invoke(initial_state)

    match_report = final_state.get("match_report") or {
        "percent_match": 0,
        "positive": [],
        "negative": [],
        "description": "No evaluation completed.",
    }

    question_sets = final_state.get("question_sets", [])
    github_questions = [q for q in question_sets if q.get("source") == "github"]

    return {
        "file_name": final_state["file_name"],
        "pdf_path": final_state["file_name"],
        "match_report": match_report,
        "question_sets": question_sets,
        "github_questions": github_questions or question_sets,
        "links": final_state.get("links", []),
        "resume_text": final_state.get("resume_text", ""),
        "errors": final_state.get("errors", []),
    }


def _run_single_candidate(app_obj, pdf_path, jd, file_name, drive_file_id):
    if app_obj:
        with app_obj.app_context():
            return run_candidate_analysis(
                pdf_path=pdf_path,
                jd=jd,
                file_name=file_name,
                drive_file_id=drive_file_id,
            )
    return run_candidate_analysis(
        pdf_path=pdf_path,
        jd=jd,
        file_name=file_name,
        drive_file_id=drive_file_id,
    )


def run_batch_candidate_analysis(
    pdf_targets: List[tuple],
    jd: str,
    max_workers: int = 2,
) -> List[Dict[str, Any]]:
    """
    Executes LangGraph analysis across multiple candidate resumes using controlled
    concurrency and per-submission caching to avoid rate-limit exhaustion.
    """
    import time
    from app.projects.analyzer.services import storage

    results = [None] * len(pdf_targets)
    app_obj = None
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            app_obj = current_app._get_current_object()
    except Exception:
        pass

    # Process sequentially or in gentle concurrency of max 2 workers
    with ThreadPoolExecutor(max_workers=min(max_workers, 2)) as executor:
        future_to_index = {}
        for idx, target in enumerate(pdf_targets):
            # target is (submission, field_name, pdf_name, drive_file_id, absolute_path)
            if len(target) == 5:
                submission, field_name, pdf_name, drive_file_id, absolute_path = target
            else:
                submission, field_name, pdf_name, absolute_path = target
                drive_file_id = None

            sub_id = str(submission.get("_id", "")) if isinstance(submission, dict) else ""

            # Check cache first
            if sub_id:
                cached = storage.get_cached_submission_analysis(sub_id, jd)
                if cached:
                    cached_copy = dict(cached)
                    cached_copy["submission_id"] = sub_id
                    cached_copy["field_name"] = field_name
                    cached_copy["file_name"] = pdf_name
                    results[idx] = cached_copy
                    continue

            future = executor.submit(
                _run_single_candidate,
                app_obj=app_obj,
                pdf_path=absolute_path,
                jd=jd,
                file_name=pdf_name,
                drive_file_id=drive_file_id,
            )
            future_to_index[future] = (idx, submission, field_name, pdf_name)

        for future in as_completed(future_to_index):
            idx, submission, field_name, pdf_name = future_to_index[future]
            sub_id = str(submission.get("_id", "")) if isinstance(submission, dict) else ""
            try:
                res = future.result()
                res["submission_id"] = sub_id
                res["field_name"] = field_name
                results[idx] = res

                # Cache result
                if sub_id:
                    storage.save_submission_analysis(sub_id, jd, res)
            except Exception as exc:
                logger.error("Error analyzing candidate %s: %s", pdf_name, exc)
                results[idx] = {
                    "file_name": pdf_name,
                    "pdf_path": pdf_name,
                    "submission_id": sub_id,
                    "field_name": field_name,
                    "match_report": {
                        "percent_match": 0,
                        "positive": [],
                        "negative": [{"description": str(exc), "keywords": []}],
                        "description": "Error during analysis",
                    },
                    "question_sets": [],
                    "github_questions": [],
                    "links": [],
                }

    return [r for r in results if r is not None]
