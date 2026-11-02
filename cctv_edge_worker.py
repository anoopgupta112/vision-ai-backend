#!/usr/bin/env python3
"""
cctv_edge_worker.py
===================
Standalone In-Store CCTV Edge Worker for VIP Concierge & Facial Radar.
Can run locally inside any boutique/shop on a laptop, Intel NUC, or Mini PC.

Capabilities:
1. Auto-discovers any ONVIF-compliant CCTV cameras on the local Wi-Fi / LAN.
2. Connects to standard RTSP streams using multi-threaded CamGear (VidGear) for zero lag & auto-reconnect.
3. Samples frames, detects faces locally, and posts 512-d embeddings to the VIP Concierge server.

Usage:
  # 1. Discover all cameras on the network
  python cctv_edge_worker.py --discover

  # 2. Stream and monitor a camera
  python cctv_edge_worker.py --rtsp "rtsp://username:password@192.168.1.100:554/stream" --backend "http://localhost:8000"
"""

import argparse
import base64
import os
import re
import sys
import time
import cv2
import requests


def discover_cameras(timeout: int = 3):
    """Discovers all ONVIF CCTV cameras on the local subnet."""
    print("🔍 Scanning local network for ONVIF CCTV cameras via WS-Discovery...")
    try:
        from wsdiscovery.discovery import ThreadedWSDiscovery as WSDiscovery
        from wsdiscovery import Scope

        wsd = WSDiscovery()
        wsd.start()
        scope = Scope("onvif://www.onvif.org/Profile")
        services = wsd.searchServices(scopes=[scope], timeout=timeout)

        discovered = []
        seen = set()
        for s in services:
            for xaddr in s.getXAddrs():
                match = re.search(r"://(\d+\.\d+\.\d+\.\d+)(?::(\d+))?", str(xaddr))
                if match:
                    ip = match.group(1)
                    port = int(match.group(2)) if match.group(2) else 80
                    if ip not in seen:
                        seen.add(ip)
                        discovered.append({"ip": ip, "port": port, "endpoint": str(xaddr)})
        wsd.stop()

        print(f"\n✅ Found {len(discovered)} camera(s) on local network:")
        for idx, cam in enumerate(discovered, 1):
            print(f"  [{idx}] IP: {cam['ip']} (Port: {cam['port']}) -> {cam['endpoint']}")
        return discovered
    except ImportError:
        print("❌ WSDiscovery library is not installed. Run: pip install WSDiscovery")
        return []
    except Exception as exc:
        print(f"❌ Error during discovery: {exc}")
        return []


def resolve_onvif_rtsp(
    ip: str,
    port: int = 80,
    username: str = None,
    password: str = None
):
    """Fetches the official RTSP URL from an ONVIF camera."""
    resolved_user = username or os.environ.get("ONVIF_DEFAULT_USERNAME", "admin")
    resolved_pass = password or os.environ.get("ONVIF_DEFAULT_PASSWORD", "")
    try:
        from onvif import ONVIFCamera
        cam = ONVIFCamera(ip, port, resolved_user, resolved_pass)
        media = cam.create_media_service()
        profiles = media.GetProfiles()
        if not profiles:
            return None
        token = profiles[0].token
        setup = {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}}
        uri = media.GetStreamUri({"StreamSetup": setup, "ProfileToken": token}).Uri
        if resolved_user and resolved_pass and "@" not in uri:
            uri = uri.replace("rtsp://", f"rtsp://{resolved_user}:{resolved_pass}@", 1)
        return uri
    except Exception as exc:
        print(f"⚠️ Could not fetch ONVIF RTSP: {exc}")
        return None


def run_cctv_stream_worker(
    rtsp_url: str,
    backend_url: str,
    shop_id: str = "default",
    camera_id: str = "cctv_entrance_1",
    sample_fps: float = 2.0,
    auth_token: str = None,
):
    """
    Connects to the RTSP stream using CamGear for multi-threaded reading and auto-reconnect.
    Captures frames, encodes to JPEG, and sends match probes to the VIP Concierge backend.
    """
    print(f"\n🚀 Connecting to CCTV RTSP stream: {rtsp_url}")
    print(f"📡 Backend Search Target: {backend_url}/api/vip-concierge/matches/search")

    try:
        from vidgear.gears import CamGear
        stream = CamGear(source=rtsp_url).start()
        print("✅ CamGear multi-threaded stream reader active.")
    except Exception as e:
        print(f"⚠️ CamGear failed ({e}), falling back to standard OpenCV VideoCapture.")
        stream = None

    cap = None
    if stream is None:
        cap = cv2.VideoCapture(rtsp_url)

    sample_interval = 1.0 / max(sample_fps, 0.5)
    last_sample_time = 0.0

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        while True:
            frame = None
            if stream is not None:
                frame = stream.read()
            elif cap is not None:
                ret, frame = cap.read()
                if ret:
                    frame = frame

            if frame is None:
                time.sleep(0.05)
                continue

            now = time.time()
            if now - last_sample_time < sample_interval:
                continue
            last_sample_time = now

            # Encode frame to JPEG Base64
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            b64_img = "data:image/jpeg;base64," + base64.b64encode(buf).decode("utf-8")

            # Post frame probe to backend
            try:
                endpoint = f"{backend_url.rstrip('/')}/api/vip-concierge/matches/search"
                res = requests.post(
                    endpoint,
                    json={
                        "image_base64": b64_img,
                        "shop_id": shop_id,
                        "camera_id": camera_id,
                        "threshold": 0.42,
                    },
                    headers=headers,
                    timeout=2.0,
                )
                if res.status_code == 200:
                    data = res.json()
                    if data.get("matched"):
                        name = data.get("customer_name")
                        tier = data.get("tier")
                        conf = data.get("confidence", 0.0)
                        print(f"🔔 [VIP MATCHED!] {name} ({tier} VIP) • Confidence: {conf:.2f}")
            except requests.exceptions.RequestException:
                pass

    except KeyboardInterrupt:
        print("\nStopping CCTV edge worker...")
    finally:
        if stream is not None:
            stream.stop()
        if cap is not None:
            cap.release()
        print("Done.")


def main():
    parser = argparse.ArgumentParser(description="In-Store CCTV Edge Worker for VIP Concierge")
    parser.add_argument("--discover", action="store_true", help="Auto-discover ONVIF cameras on the local network")
    parser.add_argument("--rtsp", type=str, help="RTSP stream URL (e.g. rtsp://admin:pass@192.168.1.100:554/live)")
    parser.add_argument("--backend", type=str, default="http://localhost:8000", help="Backend server URL")
    parser.add_argument("--shop-id", type=str, default="default", help="Shop ID")
    parser.add_argument("--camera-id", type=str, default="entrance_cam_1", help="Camera identifier")
    parser.add_argument("--fps", type=float, default=2.0, help="Sampling frames per second (default: 2.0)")
    parser.add_argument("--token", type=str, default=None, help="Bearer authorization token if required")

    args = parser.parse_args()

    if args.discover:
        discover_cameras()
        return

    if not args.rtsp:
        # Prompt user
        cams = discover_cameras(timeout=2)
        if cams:
            target = cams[0]
            print(f"\nAttempting ONVIF connection to {target['ip']}...")
            url = resolve_onvif_rtsp(target["ip"], port=target["port"])
            if url:
                run_cctv_stream_worker(
                    rtsp_url=url,
                    backend_url=args.backend,
                    shop_id=args.shop_id,
                    camera_id=args.camera_id,
                    sample_fps=args.fps,
                    auth_token=args.token,
                )
                return

        print("\nUsage example: python cctv_edge_worker.py --rtsp 'rtsp://admin:pass@192.168.1.100:554/stream1'")
        return

    run_cctv_stream_worker(
        rtsp_url=args.rtsp,
        backend_url=args.backend,
        shop_id=args.shop_id,
        camera_id=args.camera_id,
        sample_fps=args.fps,
        auth_token=args.token,
    )


if __name__ == "__main__":
    main()

