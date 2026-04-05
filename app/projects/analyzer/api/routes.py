import json
import os
import re
import tempfile
import uuid

from flask import Blueprint, jsonify, request, render_template, send_file

from app.core.exceptions import AppException, AuthorizationError, InsufficientCreditsError, NotFoundError
from app.projects.analyzer.api.payloads import CUSTOM_FIELD_TYPES, FIELD_DEFINITIONS
from app.projects.analyzer.api.templates_config import get_all_templates, get_template_by_name
from app.projects.analyzer.services import storage
from app.projects.analyzer.services.github_agent import (
    extract_experience_section,
    extract_project_section,
    generate_questions_from_experience,
    generate_questions_from_github,
    generate_questions_from_jd,
    generate_questions_from_projects,
)
from app.projects.analyzer.services.github_questions import process_uploaded_pdfs
from app.projects.analyzer.services.match_agent import evaluate_resume_against_jd
from app.projects.analyzer.services.ocr_engine import extract_text_from_pdf
from app.projects.analyzer.services.utils import get_form_submissions
from app.core.middleware import auth_required, get_current_user
from app.projects.lead_gen.credits import pipeline as credits_pipeline

bp = Blueprint("analyzer", __name__, url_prefix="/api/analyzer")

ANALYZER_CREDIT_COST_PER_TARGET = os.getenv("ANALYZER_PRICE",5)


@bp.route("", methods=["GET"])
@auth_required
def landing_page():
    return render_template("analyzer/landing.html")


@bp.route("/", methods=["GET"])
@auth_required
def landing_page_slash():
    return render_template("analyzer/landing.html")


@bp.route("/form-builder", methods=["GET"])
@auth_required
def form_builder():
    return render_template("analyzer/index.html")


@bp.route("/match_upload", methods=["GET"])
@auth_required
def upload_resumes_page():
    return render_template("analyzer/match_upload.html")


@bp.route("/match_results", methods=["GET"])
@auth_required
def match_results():
    return render_template("analyzer/match_results.html")


@bp.route("/github_questions", methods=["GET"])
@auth_required
def github_questions_page():
    return render_template("analyzer/github_questions.html")


@bp.route("/forms/<form_id>/view", methods=["GET"])
def serve_form_page(form_id):
    form = storage.get_form(form_id)
    if not form:
        return jsonify({"error": "Form not found."}), 404
    return render_template("analyzer/form.html", fields=form["fields"], form_id=form_id)


@bp.route("/analyze_pdfs/<form_id>", methods=["GET"])
@auth_required
def analyze_pdfs_page(form_id):
    try:
        user = get_current_user()
        _get_owned_form(form_id, str(user["_id"]))
        submissions = storage.get_form_submissions(form_id)
        pdf_list = []
        for sub in submissions:
            for value in sub.values():
                if isinstance(value, dict) and value.get("name"):
                    pdf_list.append({"name": value["name"], "path": value.get("path", ""), "submission_id": sub.get("id", "")})
        return render_template("analyzer/analyze_pdfs.html", form_id=form_id, pdfs=pdf_list)
    except AppException as error:
        return _json_error_response(error)


def _build_fields(selected_fields, custom_fields):
    fields = [field for field in FIELD_DEFINITIONS if field["name"] in selected_fields]
    for custom_field in custom_fields:
        field = {
            "name": custom_field["name"],
            "label": custom_field["name"].replace("_", " ").title(),
            "data_type": custom_field["data_type"],
        }
        if custom_field["data_type"] == "file" and custom_field.get("accept"):
            field["accept"] = custom_field["accept"]
        fields.append(field)
    return fields


def _json_error_response(error: AppException):
    return jsonify({"error": error.message}), error.status_code


def _analyzer_credit_amount(target_count: int) -> int:
    return max(target_count, 0) * ANALYZER_CREDIT_COST_PER_TARGET


def _require_analyzer_credits(user_id: str, target_count: int) -> int:
    required = _analyzer_credit_amount(target_count)
    if required == 0:
        return 0

    balance = credits_pipeline.get_user_balance(user_id)
    if balance < required:
        raise InsufficientCreditsError(balance, required)

    return required


def _deduct_analyzer_credits(user_id: str, amount: int, note: str):
    if amount <= 0:
        return None
    return credits_pipeline.deduct_credits(user_id, amount, note=note)


def _iter_submission_pdf_targets(submissions, selected_pdfs=None):
    selected_pdf_names = set(selected_pdfs or [])
    for submission in submissions:
        for field_name, value in submission.get("data", {}).items():
            if not isinstance(value, dict):
                continue

            absolute_path = value.get("path", "")
            if not absolute_path.lower().endswith(".pdf") or not os.path.exists(absolute_path):
                continue

            pdf_name = value.get("name") or os.path.basename(absolute_path)
            if selected_pdf_names and pdf_name not in selected_pdf_names:
                continue

            yield submission, field_name, pdf_name, absolute_path


def _get_owned_form(form_id: str, user_id: str):
    form = storage.get_form(form_id)
    if not form:
        raise NotFoundError("Form not found")
    owner_id = form.get("user_id")
    if owner_id and owner_id != user_id:
        raise AuthorizationError("Access denied")
    return form


@bp.route("/meta", methods=["GET"])
@auth_required
def meta():
    from app.projects.analyzer.services.ai_client import get_current_provider

    return jsonify(
        {
            "provider": get_current_provider(),
            "fields": FIELD_DEFINITIONS,
            "custom_types": CUSTOM_FIELD_TYPES,
            "templates": get_all_templates(),
        }
    )


@bp.route("/forms", methods=["GET"])
@auth_required
def forms():
    user = get_current_user()
    return jsonify({"forms": storage.list_forms(str(user["_id"]))})


@bp.route("/forms", methods=["POST"])
@auth_required
def create_form_record():
    user = get_current_user()
    data = request.get_json() or {}
    selected_fields = data.get("fields", [])
    custom_fields = data.get("custom_fields", [])
    template_name = data.get("template_name")
    form_name = data.get("name")

    fields = get_template_by_name(template_name) if template_name else _build_fields(selected_fields, custom_fields)
    if not fields:
        return jsonify({"error": "At least one field is required"}), 400
    if not form_name:
        return jsonify({"error": "Form name is required"}), 400

    form_id = str(uuid.uuid4())[:10]
    storage.create_form(form_id, fields, user_id=str(user["_id"]), name=form_name)
    forms_list = storage.list_forms(str(user["_id"]))
    form = next((item for item in forms_list if item["form_id"] == form_id), None)
    if form is None:
        form = {
            "id": form_id,
            "form_id": form_id,
            "name": form_name,
            "fields": fields,
            "submission_count": 0,
        }
    return jsonify({"form": form}), 201


@bp.route("/forms/<form_id>/submissions", methods=["GET"])
@auth_required
def form_submissions(form_id):
    try:
        user = get_current_user()
        _get_owned_form(form_id, str(user["_id"]))
        return jsonify({"submissions": storage.get_form_submissions(form_id)})
    except AppException as error:
        return _json_error_response(error)


@bp.route("/forms/<form_id>/submissions", methods=["POST"])
@auth_required
def create_submission_record(form_id):
    try:
        user = get_current_user()
        form = _get_owned_form(form_id, str(user["_id"]))

        submission = {}
        for field in form["fields"]:
            field_name = field["name"]
            field_type = field.get("data_type", "text")
            if field_type == "file":
                upload = request.files.get(field_name)
                if upload and upload.filename:
                    submission[field_name] = storage.save_upload(upload, f"form-{form_id}")
                else:
                    submission[field_name] = ""
            else:
                submission[field_name] = request.form.get(field_name, "")
        created = storage.add_submission(form_id, submission)
        return jsonify({"submission": {"id": str(created["_id"]), "form_id": form_id, "data": created["data"]}}), 201
    except AppException as error:
        return _json_error_response(error)


@bp.route("/forms/<form_id>/analyze", methods=["POST"])
@auth_required
def analyze_form_submissions_with_id(form_id):
    try:
        user = get_current_user()
        _get_owned_form(form_id, str(user["_id"]))
        payload = request.get_json() or {}
        job_description = payload.get("jd", "")
        submission_ids = payload.get("submission_ids", [])
        selected_pdfs = set(payload.get("selected_pdfs", []))
        submissions = storage.get_submission_documents(form_id, submission_ids=submission_ids)
        if not submissions:
            return jsonify({"matches": []}), 200

        pdf_targets = list(_iter_submission_pdf_targets(submissions, selected_pdfs))
        if not pdf_targets:
            return jsonify({"matches": []}), 200

        credits_required = _require_analyzer_credits(str(user["_id"]), len(pdf_targets))

        results = []
        for submission, field_name, pdf_name, absolute_path in pdf_targets:
            resume_text, links = extract_text_from_pdf(absolute_path)
            match_report = evaluate_resume_against_jd(job_description, resume_text)
            github_questions = []
            github_links = [item["uri"] for item in links if isinstance(item, dict) and "uri" in item]
            for github_url in sorted(set(github_links)):
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
                jd_qdata = generate_questions_from_jd(job_description, 10)
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
            for project in generate_questions_from_projects(project_text):
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
                    "submission_id": str(submission["_id"]),
                    "field_name": field_name,
                    "file_name": pdf_name,
                    "match_report": match_report,
                    "question_sets": github_questions,
                    "github_questions": github_questions,
                    "links": links,
                }
            )

        _deduct_analyzer_credits(
            str(user["_id"]),
            credits_required,
            note=f"Analyzer usage: analyzed {len(pdf_targets)} submission PDF(s) for form {form_id}",
        )
        return jsonify({"matches": results})
    except AppException as error:
        return _json_error_response(error)


@bp.route("/v1/template_fields/<name>", methods=["GET"])
@auth_required
def template_fields(name: str):
    fields = get_template_by_name(name)
    if not fields:
        return jsonify({"error": "Template not found"}), 404
    return jsonify({"fields": fields})


@bp.route("/v1/templates", methods=["GET"])
@auth_required
def templates():
    return jsonify(get_all_templates())


@bp.route("/v1/fields", methods=["GET"])
@auth_required
def fields():
    return jsonify({"fields": FIELD_DEFINITIONS, "custom_types": CUSTOM_FIELD_TYPES})


@bp.route("/v1/create_form", methods=["POST"])
@auth_required
def create_form():
    user = get_current_user()
    data = request.get_json() or {}
    selected_fields = data.get("fields", [])
    custom_fields = data.get("custom_fields", [])
    form_name = data.get("name") or "Generated Form"

    fields = _build_fields(selected_fields, custom_fields)
    if not fields:
        return jsonify({"error": "At least one field is required."}), 400

    form_id = str(uuid.uuid4())[:10]
    storage.create_form(form_id, fields, user_id=str(user["_id"]), name=form_name)
    return jsonify({"form_url": f"/api/analyzer/forms/{form_id}/view", "fields": fields, "form_id": form_id})


@bp.route("/v1/data/<form_id>", methods=["GET"])
def serve_form(form_id):
    form = storage.get_form(form_id)
    if not form:
        return jsonify({"error": "Form not found."}), 404
    return jsonify({"form_id": form_id, "name": form.get("name"), "fields": form["fields"]})


@bp.route("/v1/data/<form_id>", methods=["POST"])
def submit_form(form_id):
    form = storage.get_form(form_id)
    if not form:
        return jsonify({"error": "Form not found."}), 404

    submission = {}
    for field in form["fields"]:
        field_name = field["name"]
        field_type = field.get("data_type", "text")
        if field_type == "file":
            upload = request.files.get(field_name)
            if upload and upload.filename:
                submission[field_name] = storage.save_upload(upload, f"public-form-{form_id}")
            else:
                submission[field_name] = ""
        else:
            submission[field_name] = request.form.get(field_name, "")

    created = storage.add_submission(form_id, submission)
    payload = dict(created["data"])
    payload["id"] = str(created["_id"])
    return jsonify(payload)


@bp.route("/v1/data/<form_id>/excel", methods=["GET"])
@auth_required
def download_excel(form_id):
    try:
        user = get_current_user()
        _get_owned_form(form_id, str(user["_id"]))
        file_path = storage.export_to_excel(form_id)
    except FileNotFoundError:
        return jsonify({"error": "No data found."}), 404
    except AppException as error:
        return _json_error_response(error)
    return send_file(file_path, as_attachment=True, download_name=f"{form_id}_data.xlsx")


@bp.route("/v1/match_from_pdfs", methods=["POST"])
@auth_required
def match_from_pdfs():
    try:
        user = get_current_user()
        jd = request.form.get("jd", "")
        pdf_files = [pdf for pdf in request.files.getlist("pdf_files") if getattr(pdf, "filename", "")]
        if not pdf_files:
            return jsonify({"error": "At least one PDF is required"}), 400

        credits_required = _require_analyzer_credits(str(user["_id"]), len(pdf_files))

        with tempfile.TemporaryDirectory() as temp_dir:
            results = process_uploaded_pdfs(pdf_files, jd, temp_dir)

        _deduct_analyzer_credits(
            str(user["_id"]),
            credits_required,
            note=f"Analyzer usage: matched {len(pdf_files)} uploaded PDF(s)",
        )

        normalized = []
        for item in results:
            normalized.append(
                {
                    "file_name": item["pdf_path"],
                    "pdf_path": item["pdf_path"],
                    "match_report": item["match_report"],
                    "question_sets": item["github_questions"],
                    "github_questions": item["github_questions"],
                    "links": item["links"],
                    "resume_text": item.get("resume_text", ""),
                }
            )
        return jsonify({"matches": normalized})
    except AppException as error:
        return _json_error_response(error)


@bp.route("/v1/analyze_from_excel/<form_id>", methods=["POST"])
@auth_required
def analyze_from_excel(form_id):
    try:
        user = get_current_user()
        _get_owned_form(form_id, str(user["_id"]))
        submissions = get_form_submissions(form_id)
        if not submissions:
            return jsonify({"error": "No submissions found."}), 404

        jd = request.form.get("jd", "")
        selected_pdfs = request.form.get("selected_pdfs", "[]")
        try:
            selected_pdf_list = json.loads(selected_pdfs) if selected_pdfs else []
        except json.JSONDecodeError:
            selected_pdf_list = []

        submission_docs = storage.get_submission_documents(form_id)
        pdf_targets = list(_iter_submission_pdf_targets(submission_docs, selected_pdf_list))
        credits_required = _require_analyzer_credits(str(user["_id"]), len(pdf_targets))

        results = []
        for submission, field_name, pdf_name, absolute_path in pdf_targets:
            resume_text, links = extract_text_from_pdf(absolute_path)
            match_report = evaluate_resume_against_jd(jd, resume_text)
            github_questions = []
            github_links = [item["uri"] for item in links if isinstance(item, dict) and "uri" in item]
            repo_links = []
            for github_url in github_links:
                if re.match(r"https://github.com/[^/]+/[^/]+", github_url):
                    repo_links.append(github_url)
            for github_url in sorted(set(repo_links)):
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
            for project in generate_questions_from_projects(project_text):
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
                    "file_name": pdf_name,
                    "pdf_path": pdf_name,
                    "submission_id": str(submission["_id"]),
                    "field_name": field_name,
                    "match_report": match_report,
                    "question_sets": github_questions,
                    "github_questions": github_questions,
                    "links": links,
                }
            )

        _deduct_analyzer_credits(
            str(user["_id"]),
            credits_required,
            note=f"Analyzer usage: analyzed {len(pdf_targets)} Excel-selected PDF(s) for form {form_id}",
        )
        return jsonify(results)
    except AppException as error:
        return _json_error_response(error)


@bp.route("/v1/github_questions", methods=["POST"])
@auth_required
def github_questions():
    try:
        user = get_current_user()
        data = request.get_json() or {}
        github_urls = data.get("github_urls", [])
        num_questions = int(data.get("num_questions", 10))
        credits_required = _require_analyzer_credits(str(user["_id"]), len(github_urls))
        result = generate_questions_from_github(github_urls, num_questions)
        _deduct_analyzer_credits(
            str(user["_id"]),
            credits_required,
            note=f"Analyzer usage: generated questions for {len(github_urls)} GitHub URL(s)",
        )
        return jsonify(result)
    except AppException as error:
        return _json_error_response(error)
