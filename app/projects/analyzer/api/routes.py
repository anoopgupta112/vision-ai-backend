import json
import os
import re
import tempfile
import uuid

from flask import Blueprint, jsonify, request, render_template, send_file
from werkzeug.utils import secure_filename

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
from app.projects.analyzer.services.analysis_graph import (
    run_batch_candidate_analysis,
    run_candidate_analysis,
)
from app.projects.analyzer.services.github_questions import process_uploaded_pdfs
from app.projects.analyzer.services.match_agent import evaluate_resume_against_jd
from app.projects.analyzer.services.ocr_engine import extract_text_from_pdf
from app.projects.analyzer.services.utils import get_form_submissions
from app.core.middleware import auth_required, get_current_user
from app.projects.lead_gen.credits import pipeline as credits_pipeline
import logging

logger = logging.getLogger(__name__)

bp = Blueprint("analyzer", __name__, url_prefix="/api/analyzer")

ANALYZER_CREDIT_COST_PER_TARGET = int(os.getenv("ANALYZER_PRICE", 10))


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


@bp.route("/forms/<form_id>/view", methods=["GET", "POST"])
@bp.route("/v1/forms/<form_id>/view", methods=["GET", "POST"])
@bp.route("/forms/<form_id>/submit", methods=["POST"])
@bp.route("/v1/forms/<form_id>/submit", methods=["POST"])
def serve_form_page(form_id):
    if request.method == "POST":
        return submit_form(form_id)

    form = storage.get_form(form_id)
    if not form:
        return jsonify({"error": "Form not found."}), 404

    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"form_id": form_id, "name": form.get("name"), "fields": form["fields"]})

    return render_template("analyzer/form.html", fields=form["fields"], form_id=form_id)


@bp.route("/analyze_pdfs/<form_id>", methods=["GET"])
@auth_required
def analyze_pdfs_page(form_id):
    try:
        user = get_current_user()
        _get_owned_form(form_id, str(user["_id"]), is_admin=bool(user.get("is_admin", False)))
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
    field_req_map = {}
    field_names = []
    for item in selected_fields:
        if isinstance(item, dict):
            fname = item.get("name")
            if fname:
                field_names.append(fname)
                field_req_map[fname] = item.get("required", True)
        elif isinstance(item, str):
            field_names.append(item)
            field_req_map[item] = True

    fields = []
    for field_def in FIELD_DEFINITIONS:
        if field_def["name"] in field_names:
            field = dict(field_def)
            field["required"] = bool(field_req_map.get(field_def["name"], True))
            fields.append(field)

    for custom_field in custom_fields:
        field = {
            "name": custom_field["name"],
            "label": custom_field.get("label") or custom_field["name"].replace("_", " ").title(),
            "data_type": custom_field.get("data_type", "text"),
            "required": bool(custom_field.get("required", False)),
        }
        if custom_field.get("accept"):
            field["accept"] = custom_field["accept"]
        elif custom_field.get("data_type") == "file":
            field["accept"] = ["pdf", "doc", "docx"]
        fields.append(field)
    return fields


def _json_error_response(error: AppException):
    return jsonify({"error": error.message}), error.status_code


def _analyzer_credit_amount(target_count: int) -> int:
    try:
        price = int(os.getenv("ANALYZER_PRICE", ANALYZER_CREDIT_COST_PER_TARGET))
    except (ValueError, TypeError):
        price = 10
    return max(target_count, 0) * price


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

            drive_file_id = value.get("drive_file_id")
            absolute_path = value.get("path", "")
            pdf_name = value.get("name") or (os.path.basename(absolute_path) if absolute_path else "resume.pdf")

            if selected_pdf_names and pdf_name not in selected_pdf_names:
                continue

            if drive_file_id or (absolute_path and os.path.exists(absolute_path)):
                yield submission, field_name, pdf_name, drive_file_id, absolute_path



def _get_owned_form(form_id: str, user_id: str, is_admin: bool = False):
    form = storage.get_form(form_id)
    if not form:
        raise NotFoundError("Form not found")
    if is_admin:
        return form
    owner_id = form.get("user_id")
    if not owner_id or str(owner_id) != str(user_id):
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
    return jsonify({"forms": storage.list_forms(str(user["_id"]), is_admin=bool(user.get("is_admin", False)))})


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
    forms_list = storage.list_forms(str(user["_id"]), is_admin=bool(user.get("is_admin", False)))
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
        _get_owned_form(form_id, str(user["_id"]), is_admin=bool(user.get("is_admin", False)))
        return jsonify({"submissions": storage.get_form_submissions(form_id)})
    except AppException as error:
        return _json_error_response(error)


@bp.route("/forms/<form_id>/submissions", methods=["POST"])
@auth_required
def create_submission_record(form_id):
    try:
        user = get_current_user()
        form = _get_owned_form(form_id, str(user["_id"]), is_admin=bool(user.get("is_admin", False)))

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
        _get_owned_form(form_id, str(user["_id"]), is_admin=bool(user.get("is_admin", False)))
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

        results = run_batch_candidate_analysis(pdf_targets, job_description)

        _deduct_analyzer_credits(
            str(user["_id"]),
            credits_required,
            note=f"Analyzer usage: analyzed {len(pdf_targets)} submission PDF(s) for form {form_id}",
        )
        return jsonify({"matches": results})
    except AppException as error:
        return _json_error_response(error)
    except Exception as error:
        return jsonify({"error": str(error)}), 500


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

    json_body = request.get_json(silent=True) or {}
    submission = {}

    candidate_name = (
        request.form.get("full_name") or
        request.form.get("name") or
        request.form.get("candidate_name") or
        json_body.get("full_name") or
        json_body.get("name") or
        "Candidate"
    )

    for field in form["fields"]:
        field_name = field["name"]
        field_type = field.get("data_type", "text")
        if field_type == "file":
            upload = request.files.get(field_name)
            if upload and upload.filename:
                file_bytes = upload.read()
                filename = secure_filename(upload.filename) or "resume.pdf"

                from app.projects.analyzer.services import google_drive
                try:
                    vault_info = google_drive.ensure_vault_form_structure(form_id, form.get("name"))
                    storage._forms_collection().update_one(
                        {"form_id": form_id},
                        {"$set": {
                            "vault_folder_id": vault_info["form_folder_id"],
                            "vault_folder_url": vault_info["folder_url"],
                        }},
                    )
                    drive_uploaded = google_drive.upload_resume_stream(
                        vault_info["resumes_folder_id"],
                        file_bytes,
                        filename,
                        candidate_name,
                    )
                    submission[field_name] = {
                        "name": filename,
                        "drive_file_id": drive_uploaded["file_id"],
                        "drive_url": drive_uploaded["web_view_link"],
                    }
                except Exception as exc:
                    logger.error("Failed uploading resume to Google Drive Vault: %s", exc)
                    error_msg = str(exc)
                    if "storageQuotaExceeded" in error_msg:
                        error_msg = "Google Drive storage quota is exceeded on the master account. Please free up space in Google Drive."
                    return jsonify({"error": f"Failed to stream resume to Google Drive: {error_msg}"}), 500
            else:
                submission[field_name] = json_body.get(field_name, "")
        else:
            submission[field_name] = request.form.get(field_name) or json_body.get(field_name, "")

    created = storage.add_submission(form_id, submission)

    # Sync live Excel spreadsheet to Google Drive Vault asynchronously in background
    def _sync_vault_excel():
        try:
            from app.projects.analyzer.services import google_drive
            vault_info = google_drive.ensure_vault_form_structure(form_id, form.get("name"))
            excel_bytes = storage.export_to_excel_bytes(form_id)
            google_drive.sync_excel_stream(vault_info["form_folder_id"], excel_bytes, form.get("name"))
        except Exception as exc:
            logger.debug("Could not sync live Excel to Vault: %s", exc)

    import threading
    threading.Thread(target=_sync_vault_excel, daemon=True).start()

    payload = dict(created["data"])
    payload["id"] = str(created["_id"])
    payload["status"] = "success"
    payload["message"] = "Form submitted successfully."

    if request.accept_mimetypes.accept_html and not request.accept_mimetypes.accept_json and not request.is_json and not request.headers.get("X-Requested-With"):
        return f"""<!DOCTYPE html>
<html>
<head><title>Submission Received</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b1120; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; }}
.card {{ background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 36px 32px; max-width: 480px; width: 100%; text-align: center; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5); }}
.icon {{ width: 56px; height: 56px; background: rgba(16, 185, 129, 0.2); color: #10b981; border: 2px solid #10b981; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 28px; margin: 0 auto 20px; font-weight: bold; }}
h2 {{ margin: 0 0 10px; color: #ffffff; font-size: 22px; font-weight: 700; }}
p {{ color: #94a3b8; font-size: 14px; margin: 0; line-height: 1.6; }}
</style>
</head>
<body>
<div class="card">
  <div class="icon">✓</div>
  <h2>Application Submitted!</h2>
  <p>Thank you! Your information and resume have been recorded successfully.</p>
</div>
</body>
</html>""", 201

    return jsonify(payload), 201


@bp.route("/v1/data/<form_id>/excel", methods=["GET"])
@auth_required
def download_excel(form_id):
    try:
        user = get_current_user()
        _get_owned_form(form_id, str(user["_id"]), is_admin=bool(user.get("is_admin", False)))
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
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@bp.route("/v1/analyze_from_excel/<form_id>", methods=["POST"])
@auth_required
def analyze_from_excel(form_id):
    try:
        user = get_current_user()
        _get_owned_form(form_id, str(user["_id"]), is_admin=bool(user.get("is_admin", False)))
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

        from app.projects.analyzer.services.analysis_graph import run_batch_candidate_analysis
        results = run_batch_candidate_analysis(pdf_targets, jd, max_workers=4)

        _deduct_analyzer_credits(
            str(user["_id"]),
            credits_required,
            note=f"Analyzer usage: analyzed {len(pdf_targets)} Excel-selected PDF(s) via LangGraph for form {form_id}",
        )
        return jsonify(results)
    except AppException as error:
        return _json_error_response(error)
    except Exception as error:
        return jsonify({"error": str(error)}), 500


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
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@bp.route("/forms/<form_id>/share-drive", methods=["POST"])
@auth_required
def share_form_drive(form_id):
    """Shares the form's Google Drive vault folder with a recruiter's email."""
    try:
        user = get_current_user()
        form = _get_owned_form(form_id, str(user["_id"]), is_admin=bool(user.get("is_admin", False)))

        data = request.get_json() or {}
        email = (data.get("email") or user.get("email") or "").strip().lower()
        if not email:
            return jsonify({"error": "Email address is required."}), 400

        from app.projects.analyzer.services import google_drive
        vault_info = google_drive.ensure_vault_form_structure(form_id, form.get("name"))
        
        shared = google_drive.share_folder_with_email(vault_info["form_folder_id"], email, role="writer")

        # Record shared email in MongoDB
        storage._forms_collection().update_one(
            {"form_id": form_id},
            {
                "$addToSet": {"shared_emails": email},
                "$set": {
                    "vault_folder_id": vault_info["form_folder_id"],
                    "vault_folder_url": vault_info["folder_url"],
                }
            }
        )

        return jsonify({
            "success": True,
            "message": f"Google Drive folder successfully shared with {email}.",
            "email": email,
            "folder_url": vault_info["folder_url"],
            "shared_emails": list(set(form.get("shared_emails", []) + [email])),
        }), 200
    except AppException as exc:
        return _json_error_response(exc)
    except Exception as exc:
        logger.error("Failed sharing Drive folder for form %s: %s", form_id, exc)
        return jsonify({"error": str(exc)}), 500


@bp.route("/forms/<form_id>/drive-info", methods=["GET"])
@auth_required
def get_form_drive_info(form_id):
    """Returns Google Drive vault status and list of shared emails for a form."""
    try:
        user = get_current_user()
        form = _get_owned_form(form_id, str(user["_id"]), is_admin=bool(user.get("is_admin", False)))

        folder_url = form.get("vault_folder_url")
        shared_emails = form.get("shared_emails", [])

        if not folder_url:
            try:
                from app.projects.analyzer.services import google_drive
                vault_info = google_drive.ensure_vault_form_structure(form_id, form.get("name"))
                folder_url = vault_info["folder_url"]
                storage._forms_collection().update_one(
                    {"form_id": form_id},
                    {"$set": {
                        "vault_folder_id": vault_info["form_folder_id"],
                        "vault_folder_url": vault_info["folder_url"],
                    }}
                )
            except Exception as exc:
                logger.debug("Vault not auto-initialized: %s", exc)

        return jsonify({
            "folder_url": folder_url,
            "folder_id": form.get("vault_folder_id"),
            "shared_emails": shared_emails,
        }), 200
    except AppException as exc:
        return _json_error_response(exc)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

