import base64
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

import cv2

logger = logging.getLogger(__name__)


def mask_rtsp_url(url: str) -> str:
    """Masks credentials in RTSP URLs to prevent sensitive password leakage in logs and responses."""
    if not url:
        return ""
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", url)


def discover_onvif_cameras(timeout: int = 3) -> List[Dict[str, Any]]:
    """
    Discovers ONVIF-compliant CCTV cameras on the local network using WS-Discovery multicast.
    Returns a list of discovered camera objects with IP, ports, and hardware endpoints.
    """
    found_cameras: List[Dict[str, Any]] = []
    seen_ips = set()

    try:
        from wsdiscovery.discovery import ThreadedWSDiscovery as WSDiscovery
        from wsdiscovery import Scope

        wsd = WSDiscovery()
        wsd.start()

        # Scope for standard ONVIF profile devices
        scope = Scope("onvif://www.onvif.org/Profile")
        services = wsd.searchServices(scopes=[scope], timeout=timeout)

        for service in services:
            xaddrs = service.getXAddrs()
            for xaddr in xaddrs:
                url_str = str(xaddr)
                match = re.search(r"://(\d+\.\d+\.\d+\.\d+)(?::(\d+))?", url_str)
                if match:
                    ip = match.group(1)
                    port = int(match.group(2)) if match.group(2) else 80
                    if ip not in seen_ips:
                        seen_ips.add(ip)
                        types_list = [str(t) for t in service.getTypes()]
                        found_cameras.append({
                            "ip": ip,
                            "port": port,
                            "onvif_url": url_str,
                            "types": types_list,
                            "discovered_at": time.time(),
                        })

        wsd.stop()
    except Exception as exc:
        logger.warning("ONVIF WS-Discovery network scan encountered an issue: %s", exc)

    return found_cameras


def get_onvif_rtsp_uri(
    ip: str,
    port: int = 80,
    username: Optional[str] = None,
    password: Optional[str] = None
) -> Optional[str]:
    """
    Connects to an ONVIF camera over SOAP and requests the canonical RTSP stream URL.
    Uses environment variables ONVIF_DEFAULT_USERNAME and ONVIF_DEFAULT_PASSWORD if omitted.
    """
    resolved_user = username or os.environ.get("ONVIF_DEFAULT_USERNAME", "admin")
    resolved_pass = password or os.environ.get("ONVIF_DEFAULT_PASSWORD", "")
    try:
        from onvif import ONVIFCamera

        cam = ONVIFCamera(ip, port, resolved_user, resolved_pass)
        media_service = cam.create_media_service()
        profiles = media_service.GetProfiles()
        if not profiles:
            return None

        # Select first profile (usually standard high-res stream)
        token = profiles[0].token
        stream_setup = {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}}
        uri_obj = media_service.GetStreamUri({"StreamSetup": stream_setup, "ProfileToken": token})
        rtsp_url = uri_obj.Uri

        # Inject credentials into RTSP URL scheme if missing
        if username and password and "@" not in rtsp_url:
            rtsp_url = rtsp_url.replace("rtsp://", f"rtsp://{username}:{password}@", 1)

        return rtsp_url
    except Exception as exc:
        logger.warning("Could not extract ONVIF RTSP URI from %s:%s: %s", ip, port, exc)
        return None


def test_rtsp_snapshot(rtsp_url: str, timeout_sec: int = 4) -> Dict[str, Any]:
    """
    Attempts to connect to an RTSP stream and grab a single test frame.
    Returns success status, resolution, and JPEG Base64 thumbnail.
    """
    if not rtsp_url:
        return {"success": False, "error": "RTSP URL cannot be empty"}

    try:
        # Use OpenCV with TCP transport option to minimize packet corruption
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            # Fallback to standard
            cap = cv2.VideoCapture(rtsp_url)

        start_time = time.time()
        frame = None
        while time.time() - start_time < timeout_sec:
            ret, captured = cap.read()
            if ret and captured is not None:
                frame = captured
                break
            time.sleep(0.1)

        cap.release()

        if frame is None:
            return {"success": False, "error": "Could not grab frame within timeout"}

        h, w = frame.shape[:2]
        # Resize thumbnail to max 640px width
        if w > 640:
            scale = 640 / w
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = "data:image/jpeg;base64," + base64.b64encode(buf).decode("utf-8")

        return {
            "success": True,
            "width": w,
            "height": h,
            "preview_b64": b64,
            "message": f"Successfully connected to stream ({w}x{h})"
        }
    except Exception as exc:
        logger.error("RTSP stream test failed for %s: %s", mask_rtsp_url(rtsp_url), exc)
        return {"success": False, "error": str(exc)}


class CCTVStreamManager:
    """
    Manages background thread streaming workers for registered CCTV cameras.
    Reads frames via multi-threaded CamGear / OpenCV, runs face recognition,
    and dispatches live VIP alerts when a high-value customer walks in.
    """

    def __init__(self):
        self._active_workers: Dict[str, threading.Event] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def is_streaming(self, camera_id: str) -> bool:
        with self._lock:
            return camera_id in self._active_workers and not self._active_workers[camera_id].is_set()

    def start_camera_stream(
        self,
        camera_id: str,
        rtsp_url: str,
        shop_id: str,
        user_id: str,
        on_match_callback=None,
        sample_interval: float = 0.5,
    ) -> bool:
        """Starts a background stream worker for a camera."""
        with self._lock:
            if camera_id in self._active_workers and not self._active_workers[camera_id].is_set():
                logger.info("Camera %s is already streaming", camera_id)
                return True

            stop_event = threading.Event()
            self._active_workers[camera_id] = stop_event

            thread = threading.Thread(
                target=self._worker_loop,
                args=(camera_id, rtsp_url, shop_id, user_id, stop_event, on_match_callback, sample_interval),
                daemon=True,
                name=f"cctv_worker_{camera_id}"
            )
            self._threads[camera_id] = thread
            thread.start()
            logger.info("Started CCTV background worker for camera %s (RTSP: %s)", camera_id, mask_rtsp_url(rtsp_url))
            return True

    def stop_camera_stream(self, camera_id: str) -> bool:
        """Stops the background stream worker for a camera."""
        with self._lock:
            if camera_id in self._active_workers:
                self._active_workers[camera_id].set()
                self._active_workers.pop(camera_id, None)
                self._threads.pop(camera_id, None)
                logger.info("Stopped CCTV worker for camera %s", camera_id)
                return True
            return False

    def _worker_loop(
        self,
        camera_id: str,
        rtsp_url: str,
        shop_id: str,
        user_id: str,
        stop_event: threading.Event,
        on_match_callback,
        sample_interval: float,
    ):
        """Internal frame reading and face matching worker loop."""
        from app.projects.vip_concierge.services.face_engine import face_engine
        from app.projects.vip_concierge.services.milvus_service import milvus_client
        from app.projects.vip_concierge.services.presence_service import presence_service
        from app.projects.vip_concierge.services.gemini_concierge_agent import gemini_concierge_agent
        from app.projects.vip_concierge.services.event_broadcaster import broadcaster
        from app.projects.vip_concierge.models import storage

        stream = None
        try:
            from vidgear.gears import CamGear
            stream = CamGear(source=rtsp_url).start()
            logger.info("CamGear multi-threaded reader initialized for %s", camera_id)
        except Exception as exc:
            logger.warning("CamGear could not initialize for %s: %s; falling back to OpenCV", camera_id, exc)

        cap = None
        if stream is None:
            cap = cv2.VideoCapture(rtsp_url)

        last_sample_time = 0.0

        try:
            while not stop_event.is_set():
                frame = None
                if stream is not None:
                    frame = stream.read()
                elif cap is not None:
                    ret, frame = cap.read()
                    if not ret:
                        frame = None

                if frame is None:
                    time.sleep(0.1)
                    continue

                now = time.time()
                if now - last_sample_time < sample_interval:
                    continue
                last_sample_time = now

                # Run local face detection & vector extraction
                try:
                    # Encode frame to JPEG Base64
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    b64 = "data:image/jpeg;base64," + base64.b64encode(buf).decode("utf-8")

                    faces = face_engine.process_frame(b64)
                    if not faces:
                        continue

                    best_face = max(faces, key=lambda f: f["confidence"])
                    embedding = best_face["embedding"]

                    # Search Milvus vector database
                    search_results = milvus_client.search_faces(
                        embedding=embedding,
                        shop_id=shop_id,
                        top_k=1,
                        metric_type="COSINE",
                    )

                    if not search_results:
                        continue

                    match = search_results[0]
                    sim = match["similarity"]
                    matched_id = match["customer_id"]

                    if sim >= 0.42:
                        # Check debounce cooldown
                        if presence_service.is_on_cooldown(matched_id, camera_id):
                            continue

                        customer = storage.get_customer(matched_id, user_id=user_id)
                        if not customer:
                            continue

                        active_shop = storage.get_active_shop(user_id=user_id)
                        dossier = gemini_concierge_agent.generate_briefing(
                            customer=customer,
                            match_meta={"confidence": sim},
                            shop=active_shop,
                        )

                        visit_record = storage.record_visit(
                            customer_id=matched_id,
                            user_id=user_id,
                            shop_id=shop_id,
                            camera_id=camera_id,
                            confidence=sim,
                            alert_triggered=True,
                            live_crop_b64=best_face.get("thumbnail_b64"),
                            dossier=dossier,
                        )
                        storage.increment_visit(matched_id, user_id=user_id)
                        presence_service.mark_present(matched_id, camera_id)

                        broadcaster.broadcast_detection(
                            customer=customer,
                            visit=visit_record,
                            dossier=dossier,
                            confidence=sim,
                        )
                        logger.info("CCTV worker detected VIP %s (%s) on camera %s (sim: %.3f)", customer.get("name"), customer.get("tier"), camera_id, sim)

                except Exception as detect_exc:
                    logger.debug("Frame face check error: %s", detect_exc)

        finally:
            if stream is not None:
                try:
                    stream.stop()
                except Exception:
                    pass
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
            logger.info("CCTV worker exited cleanly for camera %s", camera_id)


cctv_manager = CCTVStreamManager()

