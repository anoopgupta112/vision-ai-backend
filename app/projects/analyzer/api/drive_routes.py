import os
import logging
from flask import Blueprint, request, jsonify, redirect
from app.core.middleware import auth_required, get_current_user
from app.projects.analyzer.services import google_drive

logger = logging.getLogger(__name__)

bp = Blueprint("drive", __name__, url_prefix="/api/drive")


@bp.route("/auth-url", methods=["GET"])
@auth_required
def get_auth_url():
    """Returns the Google OAuth 2.0 authorization URL for the current user."""
    try:
        user = get_current_user()
        user_id = str(user["_id"])
        custom_redirect = request.args.get("redirect_uri")
        url = google_drive.get_authorization_url(user_id, redirect_uri=custom_redirect)
        effective_uri = custom_redirect or os.getenv("GOOGLE_DRIVE_REDIRECT_URI", "http://localhost:8000/api/drive/callback").strip()
        logger.info("[Drive OAuth] Generated authorization URL for user %s with redirect_uri=%s", user_id, effective_uri)
        return jsonify({"auth_url": url, "redirect_uri": effective_uri}), 200
    except Exception as exc:
        logger.error("Failed generating Google auth URL: %s", exc)
        return jsonify({"error": str(exc)}), 500


@bp.route("/callback", methods=["GET"])
def oauth_callback():
    """Handles the redirect from Google's consent screen."""
    code = request.args.get("code")
    user_id = request.args.get("state")
    error = request.args.get("error")
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

    if error:
        logger.warning("Google OAuth error: %s", error)
        return redirect(f"{frontend_url}/analyzer/form-builder?drive_error={error}")

    if not code or not user_id:
        return redirect(f"{frontend_url}/analyzer/form-builder?drive_error=missing_code_or_state")

    try:
        google_drive.exchange_code_for_tokens(user_id, code)
        return redirect(f"{frontend_url}/analyzer/form-builder?drive_connected=true")
    except Exception as exc:
        logger.error("Failed exchanging code for tokens: %s", exc)
        return redirect(f"{frontend_url}/analyzer/form-builder?drive_error={str(exc)}")


@bp.route("/status", methods=["GET"])
@auth_required
def drive_status():
    """Returns whether the current user has connected their Google Drive."""
    user = get_current_user()
    user_id = str(user["_id"])
    status = google_drive.get_drive_status(user_id)
    return jsonify(status), 200


@bp.route("/disconnect", methods=["POST"])
@auth_required
def disconnect():
    """Disconnects Google Drive for the current user."""
    user = get_current_user()
    user_id = str(user["_id"])
    google_drive.disconnect_drive(user_id)
    return jsonify({"success": True, "message": "Google Drive disconnected successfully."}), 200
