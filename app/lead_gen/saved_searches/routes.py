from flask import Blueprint, jsonify, request

from app.core.exceptions import AppException
from app.core.middleware import auth_required, get_current_user
from app.lead_gen.saved_searches import model, pipeline


bp = Blueprint("lead_gen_saved_searches", __name__, url_prefix="/api/lead_gen/saved-searches")


@bp.route("", methods=["POST"])
@auth_required
def create():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    query = data.get("query", "").strip()
    keyword = data.get("keyword", "").strip()
    location = data.get("location", "").strip()
    limit = data.get("limit", 10)
    name = data.get("name")

    if not query:
        if not keyword:
            return jsonify({"error": "Keyword is required"}), 400
        if not location:
            return jsonify({"error": "Location is required"}), 400
        query = f"{keyword} in {location}"

    if not isinstance(limit, int) or limit < 1:
        return jsonify({"error": "Limit must be a positive integer"}), 400
    if limit > 100:
        return jsonify({"error": "Saved search limit must be 100 or less"}), 400

    user = get_current_user()
    try:
        saved_search = pipeline.create_saved_search(
            str(user["_id"]),
            query,
            limit,
            name=name,
            keyword=keyword or None,
            location=location or None,
        )
        return jsonify({"saved_search": model.to_response(saved_search)}), 201
    except AppException as error:
        return jsonify({"error": error.message}), error.status_code


@bp.route("", methods=["GET"])
@auth_required
def list_all():
    user = get_current_user()
    limit = request.args.get("limit", 25, type=int)
    saved_searches = pipeline.list_saved_searches(str(user["_id"]), limit=limit)
    return jsonify(
        {
            "saved_searches": [model.to_response(item) for item in saved_searches],
            "count": len(saved_searches),
        }
    ), 200


@bp.route("/<saved_search_id>", methods=["DELETE"])
@auth_required
def delete(saved_search_id):
    user = get_current_user()
    try:
        result = pipeline.delete_saved_search(saved_search_id, str(user["_id"]))
        return jsonify(result), 200
    except AppException as error:
        return jsonify({"error": error.message}), error.status_code
