from datetime import datetime

from bson import ObjectId

from app.core.database import get_collection


def _forms_collection():
    return get_collection("analyzer_forms")


def _submissions_collection():
    return get_collection("analyzer_submissions")


def create_form(user_id, name, fields, template_name=None):
    now = datetime.utcnow()
    document = {
        "user_id": user_id,
        "name": name,
        "template_name": template_name,
        "fields": fields,
        "created_at": now,
        "updated_at": now,
    }
    result = _forms_collection().insert_one(document)
    document["_id"] = result.inserted_id
    return document


def list_forms(user_id):
    return list(_forms_collection().find({"user_id": user_id}).sort("updated_at", -1))


def find_form_by_id(form_id, user_id):
    try:
        object_id = ObjectId(form_id)
    except Exception:
        return None
    return _forms_collection().find_one({"_id": object_id, "user_id": user_id})


def create_submission(form_id, user_id, data):
    document = {
        "form_id": str(form_id),
        "user_id": user_id,
        "data": data,
        "created_at": datetime.utcnow(),
    }
    result = _submissions_collection().insert_one(document)
    document["_id"] = result.inserted_id
    return document


def list_submissions(form_id, user_id):
    return list(
        _submissions_collection()
        .find({"form_id": str(form_id), "user_id": user_id})
        .sort("created_at", -1)
    )


def find_submissions(form_id, user_id, submission_ids=None):
    query = {"form_id": str(form_id), "user_id": user_id}
    if submission_ids:
        object_ids = []
        for submission_id in submission_ids:
            try:
                object_ids.append(ObjectId(submission_id))
            except Exception:
                continue
        if not object_ids:
            return []
        query["_id"] = {"$in": object_ids}
    return list(_submissions_collection().find(query).sort("created_at", -1))


def count_submissions(form_id):
    return _submissions_collection().count_documents({"form_id": str(form_id)})


def serialize_form(document):
    return {
        "id": str(document["_id"]),
        "name": document.get("name", ""),
        "template_name": document.get("template_name"),
        "fields": document.get("fields", []),
        "created_at": document.get("created_at").isoformat() if document.get("created_at") else None,
        "updated_at": document.get("updated_at").isoformat() if document.get("updated_at") else None,
        "submission_count": count_submissions(document["_id"]),
    }


def serialize_submission(document):
    return {
        "id": str(document["_id"]),
        "form_id": document.get("form_id"),
        "data": document.get("data", {}),
        "created_at": document.get("created_at").isoformat() if document.get("created_at") else None,
    }
