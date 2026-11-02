#!/usr/bin/env python3
"""
VIP Concierge - Local Edge Face Detector
=========================================
Runs locally on a shop laptop, billing PC, or edge Mini-PC.
Captures frames from a local webcam or RTSP CCTV stream, runs InsightFace
AntelopeV2 locally to detect faces and extract 512-dim biometric embeddings,
and posts matching requests to the central backend API.

Usage:
    python webcam_detector.py --camera 0
    python webcam_detector.py --camera "rtsp://username:password@camera-ip:554/stream"
"""

import argparse
import base64
import logging
import sys
import time
import cv2
import numpy as np
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VIPEdgeDetector")


def get_face_analyzer(model_name="antelopev2"):
    import insightface
    from insightface.app import FaceAnalysis

    try:
        app = FaceAnalysis(name=model_name, providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        logger.info("Initialized InsightFace model '%s'", model_name)
        return app
    except Exception as exc:
        logger.warning("Could not load '%s' (%s), trying fallback 'buffalo_l'...", model_name, exc)
        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        logger.info("Initialized fallback model 'buffalo_l'")
        return app


def crop_thumbnail_b64(frame, bbox):
    h, w, _ = frame.shape
    x1, y1, x2, y2 = [int(v) for v in bbox]
    bw, bh = x2 - x1, y2 - y1
    pad_x = int(bw * 0.2)
    pad_y = int(bh * 0.2)

    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(w, x2 + pad_x)
    y2 = min(h, y2 + pad_y)

    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        crop = frame

    crop_resized = cv2.resize(crop, (160, 160))
    _, buf = cv2.imencode(".jpg", crop_resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf).decode("utf-8")


def main():
    parser = argparse.ArgumentParser(description="VIP Concierge Local Edge Detector")
    parser.add_argument("--camera", default="0", help="Camera index (0) or RTSP URL / video path")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Backend base API URL")
    parser.add_argument("--shop-id", default="default", help="Store / Shop ID")
    parser.add_argument("--camera-id", default="entrance_cam_1", help="Camera identifier")
    parser.add_argument("--threshold", type=float, default=0.65, help="Cosine similarity threshold")
    parser.add_argument("--frame-interval", type=int, default=3, help="Process every Nth frame")
    parser.add_argument("--no-preview", action="store_true", help="Run in headless mode without GUI")
    parser.add_argument("--auth-token", default="", help="Optional JWT Bearer token for authentication")
    args = parser.parse_args()

    # Determine camera source (int for device index, str for RTSP/file)
    cam_src = int(args.camera) if args.camera.isdigit() else args.camera
    logger.info("Connecting to camera source: %s", cam_src)
    cap = cv2.VideoCapture(cam_src)

    if not cap.isOpened():
        logger.error("Failed to open video source: %s", cam_src)
        sys.exit(1)

    logger.info("Loading InsightFace engine...")
    app = get_face_analyzer()

    headers = {"Content-Type": "application/json"}
    if args.auth_token:
        headers["Authorization"] = f"Bearer {args.auth_token}"

    search_endpoint = f"{args.api_url.rstrip('/')}/api/vip-concierge/matches/search"
    logger.info("Target search endpoint: %s", search_endpoint)

    frame_count = 0
    last_detected_label = ""
    last_detected_color = (0, 255, 0)
    last_detect_time = 0

    print("\n" + "=" * 60)
    print(" VIP Concierge Local Edge Detector Running")
    print(f" Camera: {cam_src} | Backend: {args.api_url}")
    print(" Press 'q' on the preview window to exit")
    print("=" * 60 + "\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            logger.warning("Frame read failed or video ended. Retrying...")
            time.sleep(0.5)
            continue

        frame_count += 1
        h, w, _ = frame.shape

        # Process every Nth frame
        if frame_count % args.frame_interval == 0:
            faces = app.get(frame)
            if faces:
                for face in faces:
                    normed_emb = getattr(face, "normed_embedding", None)
                    if normed_emb is None and hasattr(face, "embedding"):
                        norm = np.linalg.norm(face.embedding)
                        normed_emb = face.embedding / (norm + 1e-9)

                    if normed_emb is None:
                        continue

                    bbox = face.bbox.tolist()
                    thumb_b64 = crop_thumbnail_b64(frame, bbox)

                    payload = {
                        "embedding": normed_emb.tolist(),
                        "thumbnail_b64": thumb_b64,
                        "shop_id": args.shop_id,
                        "camera_id": args.camera_id,
                        "threshold": args.threshold,
                    }

                    try:
                        resp = requests.post(search_endpoint, json=payload, headers=headers, timeout=2.0)
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("matched"):
                                name = data.get("customer_name", "VIP")
                                conf = data.get("confidence", 0.0)
                                alerted = data.get("alert_triggered", False)
                                last_detected_label = f"VIP: {name} ({conf*100:.1f}%)"
                                last_detected_color = (0, 255, 0) if alerted else (0, 200, 255)
                                last_detect_time = time.time()
                                logger.info("MATCH: %s | Conf: %.3f | Alerted: %s", name, conf, alerted)
                            else:
                                last_detected_label = "Visitor (Non-VIP)"
                                last_detected_color = (200, 200, 200)
                                last_detect_time = time.time()
                    except Exception as exc:
                        logger.error("API error contacting backend: %s", exc)

        # Draw status overlay on preview
        if not args.no_preview:
            # Clear label after 3 seconds of no detection
            if time.time() - last_detect_time > 3.0:
                last_detected_label = "Monitoring..."
                last_detected_color = (150, 150, 150)

            # Draw top HUD
            cv2.rectangle(frame, (0, 0), (w, 50), (20, 20, 20), -1)
            cv2.putText(
                frame,
                f"VIP Concierge Radar | {last_detected_label}",
                (15, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                last_detected_color,
                2,
            )

            cv2.imshow("VIP Concierge Edge Detector", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

