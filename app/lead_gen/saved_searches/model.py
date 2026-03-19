from datetime import datetime

from bson import ObjectId

from app.core.database import get_collection


COLLECTION = "saved_searches"


def _coerce_id(value):
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    return value


def create_doc(user_id, query, limit, name=None, keyword=None, location=None):
    user_id = _coerce_id(user_id)
    query = query.strip()
    keyword = keyword.strip() if isinstance(keyword, str) and keyword.strip() else None
    location = location.strip() if isinstance(location, str) and location.strip() else None

    if not query and keyword and location:
        query = f"{keyword} in {location}"

    if not query:
        raise ValueError("Query is required")

    generated_name = name.strip() if isinstance(name, str) and name.strip() else query

    return {
        "user_id": user_id,
        "name": generated_name,
        "query": query,
        "keyword": keyword,
        "location": location,
        "limit": limit,
        "query_preview": query,
        "created_at": datetime.utcnow(),
    }


def to_response(doc):
    if not doc:
        return None

    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "query": doc["query"],
        "keyword": doc.get("keyword"),
        "location": doc.get("location"),
        "limit": doc["limit"],
        "query_preview": doc["query_preview"],
        "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
    }


def create(user_id, query, limit, name=None, keyword=None, location=None):
    coll = get_collection(COLLECTION)
    doc = create_doc(user_id, query, limit, name=name, keyword=keyword, location=location)
    result = coll.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def list_by_user(user_id, limit=25):
    coll = get_collection(COLLECTION)
    user_id = _coerce_id(user_id)
    return list(coll.find({"user_id": user_id}).sort("created_at", -1).limit(limit))


def find_by_id(saved_search_id):
    coll = get_collection(COLLECTION)
    saved_search_id = _coerce_id(saved_search_id)
    return coll.find_one({"_id": saved_search_id})


def delete_for_user(saved_search_id, user_id):
    coll = get_collection(COLLECTION)
    saved_search_id = _coerce_id(saved_search_id)
    user_id = _coerce_id(user_id)
    return coll.delete_one({"_id": saved_search_id, "user_id": user_id})
