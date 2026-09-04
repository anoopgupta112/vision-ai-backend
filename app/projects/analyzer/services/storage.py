import os
import io
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
        "drive_folder_id": form.get("drive_folder_id"),
        "drive_folder_name": form.get("drive_folder_name"),
        "drive_folder_url": form.get("drive_folder_url"),
        "vault_folder_id": form.get("vault_folder_id"),
        "vault_folder_url": form.get("vault_folder_url"),
        "shared_emails": form.get("shared_emails", []),
        "submissions": [submission.get("data", {}) for submission in submissions],
        "submission_docs": submissions,
        "created_at": form.get("created_at"),
        "updated_at": form.get("updated_at"),
    }


def list_forms(user_id: str = None, is_admin: bool = False):
    if is_admin:
        query = {}
    elif not user_id:
        return []
    else:
        query_conditions = [{"user_id": str(user_id)}]
        try:
            query_conditions.append({"user_id": ObjectId(user_id)})
        except Exception:
            pass
        query = {"$or": query_conditions}

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
                "drive_folder_id": form.get("drive_folder_id"),
                "drive_folder_name": form.get("drive_folder_name"),
                "drive_folder_url": form.get("drive_folder_url"),
                "vault_folder_id": form.get("vault_folder_id"),
                "vault_folder_url": form.get("vault_folder_url"),
                "shared_emails": form.get("shared_emails", []),
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


def _prepare_excel_rows(submissions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cleans submission data for Excel export: formats file fields as Google Drive URLs."""
    rows = []
    for sub in submissions:
        clean_row = {}
        for k, v in sub.items():
            if k == "id":
                continue
            if isinstance(v, dict):
                # Format uploaded files as Google Drive direct link or clean file name
                if v.get("drive_url"):
                    clean_row[k] = v["drive_url"]
                elif v.get("name"):
                    clean_row[k] = v["name"]
                else:
                    clean_row[k] = str(v)
            else:
                clean_row[k] = v
        rows.append(clean_row)
    return rows


def export_to_excel_bytes(form_id: str) -> bytes:
    """Generates the Excel export directly in memory as bytes (0 VPS disk usage)."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is not installed.") from exc

    submissions = get_form_submissions(form_id)
    if not submissions:
        raise FileNotFoundError("No submissions found.")

    clean_rows = _prepare_excel_rows(submissions)
    output = io.BytesIO()
    pd.DataFrame(clean_rows).to_excel(output, index=False)
    return output.getvalue()


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
    clean_rows = _prepare_excel_rows(submissions)
    pd.DataFrame(clean_rows).to_excel(export_path, index=False)
    return export_path


def _hash_jd(jd: str) -> str:
    import hashlib
    return hashlib.sha256(jd.strip().encode("utf-8")).hexdigest()[:16]


def get_cached_submission_analysis(submission_id: str, jd: str):
    try:
        sub = _submissions_collection().find_one({"_id": ObjectId(submission_id)})
        if sub and "analysis_cache" in sub:
            jd_key = _hash_jd(jd)
            return sub["analysis_cache"].get(jd_key)
    except Exception:
        pass
    return None


def save_submission_analysis(submission_id: str, jd: str, analysis: Dict[str, Any]) -> None:
    try:
        jd_key = _hash_jd(jd)
        _submissions_collection().update_one(
            {"_id": ObjectId(submission_id)},
            {"$set": {f"analysis_cache.{jd_key}": analysis}},
            upsert=False,
        )
    except Exception:
        pass


