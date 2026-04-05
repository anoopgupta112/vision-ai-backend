import os
from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

from bson import ObjectId
from flask import current_app
from werkzeug.utils import secure_filename

from app.core.database import get_collection


def _forms_collection():
    return get_collection("hr_forms")


def _submissions_collection():
    return get_collection("hr_submissions")


def create_form(form_id: str, fields: List[Dict[str, Any]], user_id: str = None, name: str = None):
    now = datetime.utcnow()
    document = {
        "form_id": form_id,
        "fields": fields,
        "user_id": user_id,
        "name": name or f"Form {form_id}",
        "created_at": now,
        "updated_at": now,
    }
    _forms_collection().insert_one(document)
    return document


def get_form(form_id: str):
    form = _forms_collection().find_one({"form_id": form_id})
    if not form:
        return None
    submissions = list(_submissions_collection().find({"form_id": form_id}).sort("created_at", -1))
    return {
        "id": str(form.get("_id")),
        "form_id": form["form_id"],
        "user_id": str(form["user_id"]) if form.get("user_id") is not None else None,
        "name": form.get("name"),
        "fields": form.get("fields", []),
        "submissions": [submission.get("data", {}) for submission in submissions],
        "submission_docs": submissions,
        "created_at": form.get("created_at"),
        "updated_at": form.get("updated_at"),
    }


def list_forms(user_id: str = None):
    query = {"user_id": user_id} if user_id else {}
    forms = list(_forms_collection().find(query).sort("updated_at", -1))
    result = []
    for form in forms:
        result.append(
            {
                "id": str(form["_id"]),
                "form_id": form["form_id"],
                "name": form.get("name"),
                "template_name": form.get("template_name"),
                "fields": form.get("fields", []),
                "submission_count": _submissions_collection().count_documents({"form_id": form["form_id"]}),
                "created_at": form.get("created_at").isoformat() if form.get("created_at") else None,
                "updated_at": form.get("updated_at").isoformat() if form.get("updated_at") else None,
            }
        )
    return result


def save_upload(upload, folder: str = ""):
    upload_root = os.path.abspath(current_app.config.get("ANALYZER_UPLOAD_DIR", "uploads/analyzer"))
    target_dir = os.path.join(upload_root, folder) if folder else upload_root
    os.makedirs(target_dir, exist_ok=True)
    safe_name = f"{uuid4().hex}_{secure_filename(upload.filename)}"
    absolute_path = os.path.join(target_dir, safe_name)
    upload.save(absolute_path)
    return {
        "name": upload.filename,
        "path": absolute_path,
        "relative_path": os.path.relpath(absolute_path, os.getcwd()),
        "size": os.path.getsize(absolute_path),
    }


def add_submission(form_id: str, submission: Dict[str, Any]):
    document = {"form_id": form_id, "data": submission, "created_at": datetime.utcnow()}
    result = _submissions_collection().insert_one(document)
    document["_id"] = result.inserted_id
    _forms_collection().update_one({"form_id": form_id}, {"$set": {"updated_at": datetime.utcnow()}})
    return document


def get_form_submissions(form_id: str):
    submissions = list(_submissions_collection().find({"form_id": form_id}).sort("created_at", -1))
    result = []
    for submission in submissions:
        payload = dict(submission.get("data", {}))
        payload["id"] = str(submission["_id"])
        result.append(payload)
    return result


def get_submission_documents(form_id: str, submission_ids=None):
    query = {"form_id": form_id}
    if submission_ids:
        object_ids = []
        for submission_id in submission_ids:
            try:
                object_ids.append(ObjectId(submission_id))
            except Exception:
                continue
        if object_ids:
            query["_id"] = {"$in": object_ids}
    return list(_submissions_collection().find(query).sort("created_at", -1))


def export_to_excel(form_id: str) -> str:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is not installed.") from exc

    submissions = get_form_submissions(form_id)
    if not submissions:
        raise FileNotFoundError("No submissions found.")
    export_dir = os.path.abspath(os.path.join(current_app.config.get("ANALYZER_UPLOAD_DIR", "uploads/analyzer"), "exports"))
    os.makedirs(export_dir, exist_ok=True)
    export_path = os.path.join(export_dir, f"{form_id}_data.xlsx")
    pd.DataFrame(submissions).to_excel(export_path, index=False)
    return export_path
