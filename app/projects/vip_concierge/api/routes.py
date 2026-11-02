import json
import logging
import queue
import time
from typing import Any, Dict
from flask import Blueprint, Response, jsonify, request, stream_with_context

from app.core.middleware import auth_required, get_current_user
from app.projects.vip_concierge.models import storage
from app.projects.vip_concierge.models.templates import list_templates, get_template
from app.projects.vip_concierge.services.event_broadcaster import broadcaster
from app.projects.vip_concierge.services.face_engine import face_engine
from app.projects.vip_concierge.services.gemini_concierge_agent import gemini_concierge_agent
from app.projects.vip_concierge.services.milvus_service import milvus_client
from app.projects.vip_concierge.services.presence_service import presence_service
from app.projects.vip_concierge.services.shop_agent import shop_consultant_agent
from app.projects.vip_concierge.services.cctv_service import (
    discover_onvif_cameras,
    test_rtsp_snapshot,
    cctv_manager,
    mask_rtsp_url,
)

logger = logging.getLogger(__name__)

bp = Blueprint("vip_concierge", __name__, url_prefix="/api/vip-concierge")


def current_user_id() -> str:
    user = get_current_user() or {}
    return str(user.get("_id") or user.get("id") or "")


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "vip_concierge",
        "milvus_connected": milvus_client.connected,
    }), 200


# ==============================================================================
# Customer Management & Enrollment
# ==============================================================================

@bp.route("/customers", methods=["GET"])
@auth_required
def get_customers():
    user_id = current_user_id()
    shop_id = request.args.get("shop_id")
    limit = min(int(request.args.get("limit", 50)), 100)
    skip = int(request.args.get("skip", 0))

    customers = storage.list_customers(user_id=user_id, shop_id=shop_id, limit=limit, skip=skip)
    return jsonify({"customers": customers}), 200


@bp.route("/customers", methods=["POST"])
@auth_required
def add_customer():
    user_id = current_user_id()
    data = request.get_json() or {}

    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Customer name is required"}), 400

    new_customer = storage.create_customer(user_id=user_id, data=data)

    # If photo base64 is provided directly on creation, auto-enroll face
    photo_b64 = data.get("photo_base64")
    face_enrolled = False
    warning = None
    if photo_b64:
        faces = face_engine.process_frame(photo_b64)
        if faces:
            best_face = max(faces, key=lambda f: f["confidence"])
            milvus_client.insert_face_embedding(
                customer_id=new_customer["id"],
                shop_id=new_customer.get("shop_id", "default"),
                embedding=best_face["embedding"],
            )
            storage.update_customer(
                customer_id=new_customer["id"],
                user_id=user_id,
                updates={
                    "registered_face_thumbnail": best_face["thumbnail_b64"],
                    "face_embedding": best_face["embedding"],
                },
            )
            new_customer["registered_face_thumbnail"] = best_face["thumbnail_b64"]
            new_customer["face_enrolled"] = True
            face_enrolled = True
            logger.info("Successfully enrolled face for customer %s (%s)", new_customer["id"], new_customer["name"])
        else:
            new_customer["face_enrolled"] = False
            warning = "Customer created, but no face was detected in the photo. Please upload a clear front-facing portrait."
            logger.warning("No face detected for customer %s in uploaded photo", new_customer["id"])

    return jsonify({"customer": new_customer, "face_enrolled": face_enrolled, "warning": warning}), 201


@bp.route("/customers/<customer_id>", methods=["GET"])
@auth_required
def get_single_customer(customer_id):
    user_id = current_user_id()
    customer = storage.get_customer(customer_id=customer_id, user_id=user_id)
    if not customer:
        return jsonify({"error": "Customer not found"}), 404
    return jsonify({"customer": customer}), 200


@bp.route("/customers/<customer_id>", methods=["PUT"])
@auth_required
def update_single_customer(customer_id):
    user_id = current_user_id()
    data = request.get_json() or {}
    updated = storage.update_customer(customer_id=customer_id, user_id=user_id, updates=data)
    if not updated:
        return jsonify({"error": "Customer not found or not modified"}), 404
    return jsonify({"customer": updated}), 200


@bp.route("/customers/<customer_id>", methods=["DELETE"])
@auth_required
def delete_single_customer(customer_id):
    user_id = current_user_id()
    deleted = storage.delete_customer(customer_id=customer_id, user_id=user_id)
    if not deleted:
        return jsonify({"error": "Customer not found"}), 404
    # Also remove from Milvus
    milvus_client.delete_customer_faces(customer_id=customer_id)
    return jsonify({"message": "Customer deleted successfully"}), 200


@bp.route("/customers/<customer_id>/enroll-face", methods=["POST"])
@auth_required
def enroll_customer_face(customer_id):
    """Enrolls a face for an existing customer using an uploaded image or base64 photo."""
    user_id = current_user_id()
    customer = storage.get_customer(customer_id=customer_id, user_id=user_id)
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    # Extract image from multipart form or json
    image_input = None
    if "photo" in request.files:
        image_input = request.files["photo"]
    elif request.is_json:
        image_input = (request.get_json() or {}).get("photo_base64")

    if not image_input:
        return jsonify({"error": "No photo file or photo_base64 provided"}), 400

    faces = face_engine.process_frame(image_input)
    if not faces:
        return jsonify({"error": "No face detected in photo. Please upload a clear front-facing portrait."}), 400

    best_face = max(faces, key=lambda f: f["confidence"])

    # Insert into Milvus
    milvus_client.insert_face_embedding(
        customer_id=customer["id"],
        shop_id=customer.get("shop_id", "default"),
        embedding=best_face["embedding"],
    )

    # Save thumbnail and vector to customer doc
    updated = storage.update_customer(
        customer_id=customer["id"],
        user_id=user_id,
        updates={
            "registered_face_thumbnail": best_face["thumbnail_b64"],
            "face_embedding": best_face["embedding"],
        },
    )

    return jsonify({
        "message": "Face biometric successfully registered in Milvus",
        "confidence": best_face["confidence"],
        "customer": updated,
    }), 200


# ==============================================================================
# Face Matching & Edge Detection Ingestion
# ==============================================================================

@bp.route("/matches/search", methods=["POST"])
@auth_required
def search_face_match():
    """
    Called by authorized local edge detector, CCTV stream worker, or test probe.
    Requires authentication to prevent unauthorized facial probing and PII exfiltration.
    Accepts either:
    1. Pre-computed 512-dim embedding: { "embedding": [...], "thumbnail_b64": "...", "camera_id": "..." }
    2. Raw image: { "image_base64": "..." } or multipart file 'image'
    """
    user_id = current_user_id()
    data = request.get_json(silent=True) or {}
    shop_id = data.get("shop_id", "default")
    camera_id = data.get("camera_id", "webcam_entrance")
    threshold = float(data.get("threshold", 0.50))

    embedding = data.get("embedding")
    thumbnail_b64 = data.get("thumbnail_b64", "")

    # If raw image was posted instead of precomputed vector, compute locally on server
    if not embedding:
        raw_img = None
        if "image" in request.files:
            raw_img = request.files["image"]
        elif "image_base64" in data:
            raw_img = data["image_base64"]

        if raw_img:
            faces = face_engine.process_frame(raw_img)
            if not faces:
                logger.info("Probe search: no face detected in probe image")
                return jsonify({"matched": False, "reason": "no_face_detected"}), 200
            best_face = max(faces, key=lambda f: f["confidence"])
            embedding = best_face["embedding"]
            thumbnail_b64 = best_face["thumbnail_b64"]
            logger.info("Probe search: face detected with det_score=%.3f", best_face["confidence"])

    if not embedding:
        return jsonify({"error": "Either embedding vector (512-d) or image is required"}), 400

    # 1. Search Milvus Vector Database
    match = milvus_client.search_face(
        query_embedding=embedding,
        shop_id=shop_id if shop_id != "default" else None,
        threshold=threshold,
    )

    if not match or not match.get("matched"):
        best_score = match.get("best_score", 0.0) if match else 0.0
        logger.info("Probe below threshold: best_score=%.3f (threshold=%.2f)", best_score, threshold)
        return jsonify({
            "matched": False,
            "reason": "below_threshold" if best_score > 0 else "no_match_found",
            "highest_similarity": best_score,
            "threshold": threshold,
        }), 200

    customer_id = match["customer_id"]
    confidence = match["confidence"]
    logger.info("MATCH FOUND: Customer %s with confidence %.3f", customer_id, confidence)

    # 2. Check Debounce & Cooldown
    ignore_cooldown = bool(data.get("ignore_cooldown", False))
    if ignore_cooldown:
        should_alert = True
        elapsed_seconds = 0.0
    else:
        should_alert, elapsed_seconds = presence_service.register_detection(customer_id, camera_id)

    # 3. Retrieve Customer Profile (strictly scoped to authenticated tenant)
    customer = storage.get_customer(customer_id, user_id=user_id)
    if not customer:
        return jsonify({"matched": False, "reason": "no_match_found"}), 200

    dossier = None
    visit_event = None

    if should_alert:
        # Retrieve active or specified shop profile for customized greeting & recommendations
        shop = storage.get_shop(shop_id, user_id=customer.get("user_id")) if shop_id != "default" else None
        if not shop:
            shop = storage.get_active_shop(user_id=customer.get("user_id"))

        # 4. Generate 3-second briefing via Gemini
        dossier = gemini_concierge_agent.generate_briefing(customer, match, shop=shop)

        # 5. Log Visit Event
        visit_event = storage.log_visit({
            "customer_id": customer_id,
            "user_id": customer.get("user_id"),
            "shop_id": shop_id,
            "camera_id": camera_id,
            "confidence": confidence,
            "alert_triggered": True,
            "live_crop_b64": thumbnail_b64,
            "dossier": dossier,
        })

        # 6. Broadcast Real-Time Alert to Connected Staff Tablets
        broadcaster.broadcast("vip_detected", {
            "visit": visit_event,
            "customer": customer,
            "dossier": dossier,
            "timestamp": time.time(),
        })

    return jsonify({
        "matched": True,
        "customer_id": customer_id,
        "customer_name": customer["name"],
        "tier": customer.get("tier"),
        "confidence": confidence,
        "alert_triggered": should_alert,
        "cooldown_active": not should_alert,
        "dossier": dossier,
    }), 200


# ==============================================================================
# Live Events & Visits Feed
# ==============================================================================

@bp.route("/visits", methods=["GET"])
@auth_required
def get_visits():
    user_id = current_user_id()
    shop_id = request.args.get("shop_id")
    limit = min(int(request.args.get("limit", 30)), 100)
    visits = storage.list_recent_visits(user_id=user_id, shop_id=shop_id, limit=limit)
    return jsonify({"visits": visits}), 200


@bp.route("/visits/<visit_id>/action", methods=["POST"])
@auth_required
def action_visit(visit_id):
    data = request.get_json() or {}
    status = data.get("status", "greeted")  # greeted | dismissed
    staff_notes = data.get("staff_notes", "")
    success = storage.update_visit_status(visit_id, status=status, staff_notes=staff_notes)
    if not success:
        return jsonify({"error": "Visit not found"}), 404
    return jsonify({"message": f"Visit marked as {status}"}), 200


# ==============================================================================
# Camera / CCTV Management
# ==============================================================================

@bp.route("/cameras", methods=["GET"])
@auth_required
def get_cameras():
    user_id = current_user_id()
    shop_id = request.args.get("shop_id")
    cameras = storage.list_cameras(user_id=user_id, shop_id=shop_id)
    for c in cameras:
        c["is_streaming"] = cctv_manager.is_streaming(c.get("id"))
        if "rtsp_url" in c:
            c["rtsp_url"] = mask_rtsp_url(c["rtsp_url"])
    return jsonify({"cameras": cameras}), 200


@bp.route("/cameras/discover", methods=["POST"])
@auth_required
def discover_cameras():
    """Scans local Wi-Fi / Ethernet network for any ONVIF-compliant CCTV cameras."""
    timeout = int((request.get_json() or {}).get("timeout", 3))
    devices = discover_onvif_cameras(timeout=timeout)
    return jsonify({"cameras": devices, "count": len(devices)}), 200


@bp.route("/cameras/test-stream", methods=["POST"])
@auth_required
def test_camera_stream():
    """Connects to an RTSP camera stream and grabs a test preview snapshot."""
    data = request.get_json() or {}
    rtsp_url = (data.get("rtsp_url") or "").strip()
    if not rtsp_url:
        return jsonify({"error": "RTSP stream URL is required"}), 400

    result = test_rtsp_snapshot(rtsp_url=rtsp_url)
    return jsonify(result), 200


@bp.route("/cameras/<camera_id>/start-stream", methods=["POST"])
@auth_required
def start_camera_stream(camera_id):
    """Starts active background CCTV stream monitoring for real-time VIP face matching."""
    user_id = current_user_id()
    camera = storage.get_camera(camera_id, user_id=user_id)
    if not camera:
        return jsonify({"error": "Camera not found"}), 404

    rtsp_url = camera.get("rtsp_url")
    if not rtsp_url:
        return jsonify({"error": "Camera has no configured RTSP stream URL"}), 400

    shop_id = camera.get("shop_id") or "default"
    started = cctv_manager.start_camera_stream(
        camera_id=camera_id,
        rtsp_url=rtsp_url,
        shop_id=shop_id,
        user_id=user_id,
    )
    return jsonify({"message": "CCTV live AI stream started", "camera_id": camera_id, "active": started}), 200


@bp.route("/cameras/<camera_id>/stop-stream", methods=["POST"])
@auth_required
def stop_camera_stream(camera_id):
    """Stops background CCTV stream monitoring."""
    stopped = cctv_manager.stop_camera_stream(camera_id)
    return jsonify({"message": "CCTV stream stopped", "camera_id": camera_id, "active": False}), 200


@bp.route("/cameras", methods=["POST"])
@auth_required
def add_camera():
    user_id = current_user_id()
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Camera name is required"}), 400
    camera = storage.create_camera(user_id=user_id, data=data)
    camera["is_streaming"] = False
    if "rtsp_url" in camera:
        camera["rtsp_url"] = mask_rtsp_url(camera["rtsp_url"])
    return jsonify({"camera": camera}), 201


@bp.route("/cameras/<camera_id>", methods=["DELETE"])
@auth_required
def remove_camera(camera_id):
    user_id = current_user_id()
    cctv_manager.stop_camera_stream(camera_id)
    deleted = storage.delete_camera(camera_id=camera_id, user_id=user_id)
    if not deleted:
        return jsonify({"error": "Camera not found"}), 404
    return jsonify({"message": "Camera removed successfully"}), 200


@bp.route("/events/stream", methods=["GET"])
@auth_required
def event_stream():
    """Server-Sent Events (SSE) endpoint for real-time alerts."""
    def stream():
        q = broadcaster.listen()
        try:
            # Send initial keepalive
            yield f"event: connected\ndata: {json.dumps({'status': 'listening'})}\n\n"
            while True:
                try:
                    msg = q.get(timeout=25.0)
                    yield msg
                except queue.Empty:
                    # Keep-alive heartbeat
                    yield ": ping\n\n"
        except GeneratorExit:
            broadcaster.unlisten(q)

    return Response(stream_with_context(stream()), mimetype="text/event-stream")


@bp.route("/stats", methods=["GET"])
@auth_required
def get_stats():
    user_id = current_user_id()
    customers = storage.list_customers(user_id=user_id, limit=500)
    visits = storage.list_recent_visits(user_id=user_id, limit=100)

    total_vips = len(customers)
    total_spent = sum(c.get("total_spent", 0) for c in customers)
    total_visits = sum(c.get("visit_count", 0) for c in customers)

    return jsonify({
        "total_vips": total_vips,
        "total_portfolio_spend": total_spent,
        "total_recorded_visits": total_visits,
        "recent_alerts_count": len([v for v in visits if v.get("status") == "new"]),
    }), 200


# ==============================================================================
# Shop Configuration & LangChain AI Consultant Endpoints
# ==============================================================================

@bp.route("/shops/templates", methods=["GET"])
@auth_required
def get_shop_templates():
    """Returns database-backed industry templates and blueprints."""
    templates = list_templates()
    return jsonify({"templates": templates}), 200


@bp.route("/shops/agent/welcome", methods=["GET"])
@auth_required
def get_agent_welcome():
    """Returns dynamic initial greeting and suggested prompts from the LangChain AI Consultant."""
    user_id = current_user_id()
    shop_id = request.args.get("shop_id")
    shop = None
    if shop_id:
        shop = storage.get_shop(shop_id, user_id=user_id)
    if not shop:
        shop = storage.get_active_shop(user_id=user_id)

    welcome_data = shop_consultant_agent.get_agent_welcome(current_config=shop)
    return jsonify({"welcome": welcome_data}), 200


@bp.route("/shops", methods=["GET"])
@auth_required
def get_shops():
    user_id = current_user_id()
    shops = storage.list_shops(user_id=user_id)
    active_shop = storage.get_active_shop(user_id=user_id)
    return jsonify({"shops": shops, "active_shop": active_shop}), 200


@bp.route("/shops/active", methods=["GET"])
@auth_required
def get_active_shop():
    user_id = current_user_id()
    shop = storage.get_active_shop(user_id=user_id)
    return jsonify({"shop": shop}), 200


@bp.route("/shops", methods=["POST"])
@auth_required
def save_shop():
    user_id = current_user_id()
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Store / Shop name is required"}), 400

    saved = storage.upsert_shop(user_id=user_id, data=data)
    return jsonify({"shop": saved, "message": "Shop configuration saved successfully"}), 200


@bp.route("/shops/<shop_id>/activate", methods=["POST"])
@auth_required
def activate_shop(shop_id):
    user_id = current_user_id()
    success = storage.set_active_shop(user_id=user_id, shop_id=shop_id)
    if not success:
        return jsonify({"error": "Shop not found"}), 404
    active = storage.get_shop(shop_id, user_id=user_id)
    return jsonify({"message": "Shop activated", "shop": active}), 200


@bp.route("/shops/agent/chat", methods=["POST"])
@auth_required
def consult_shop_agent():
    """
    LangChain AI Shop Consultant chat endpoint.
    Accepts conversational inputs from the shop owner, asks clarifying questions,
    and returns a tailored draft shop configuration.
    """
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Message is required"}), 400

    chat_history = data.get("chat_history") or []
    current_config = data.get("current_config") or {}

    consultation = shop_consultant_agent.consult(
        user_message=message,
        chat_history=chat_history,
        current_config=current_config,
    )
    return jsonify(consultation), 200


@bp.route("/shops/agent/generate", methods=["POST"])
@auth_required
def generate_shop_preset():
    """
    Fast-track generation: Creates or adapts an industry blueprint (clothing, jewelry, watches, etc.)
    using LangChain.
    """
    data = request.get_json() or {}
    industry = (data.get("industry") or "clothing").strip().lower()
    store_name = (data.get("store_name") or "").strip() or None
    details = (data.get("details") or "").strip() or None

    config = shop_consultant_agent.generate_preset(
        industry=industry,
        store_name=store_name,
        details=details,
    )
    return jsonify({"shop": config}), 200

