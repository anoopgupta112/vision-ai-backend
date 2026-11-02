import base64
import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class FaceEngine:
    def __init__(self, model_name: str = "antelopev2"):
        self.model_name = model_name
        self._app = None
        self._initialized = False
        self._current_det_size = (640, 640)
        self._current_det_thresh = 0.4

    def _ensure_det_params(self, det_size: Tuple[int, int] = (640, 640), det_thresh: float = 0.4):
        if self._app is None:
            return
        if self._current_det_size != det_size or abs(self._current_det_thresh - det_thresh) > 1e-3:
            try:
                self._app.prepare(ctx_id=-1, det_thresh=det_thresh, det_size=det_size)
                self._current_det_size = det_size
                self._current_det_thresh = det_thresh
            except Exception as e:
                logger.debug("Failed setting det_size %s: %s", det_size, e)

    def initialize(self) -> bool:
        if self._initialized:
            return True
        try:
            import cv2
            import insightface
            from insightface.app import FaceAnalysis

            models_dir = Path.home() / ".insightface" / "models"
            antelope_dir = models_dir / "antelopev2"
            model_to_use = "antelopev2" if antelope_dir.is_dir() else "buffalo_l"

            try:
                self._app = FaceAnalysis(name=model_to_use, providers=["CPUExecutionProvider"])
                self._app.prepare(ctx_id=-1, det_thresh=0.4, det_size=(640, 640))
                self._current_det_size = (640, 640)
                self._current_det_thresh = 0.4
                self._initialized = True
                logger.info("InsightFace successfully initialized with model '%s'", model_to_use)
                return True
            except Exception as e_primary:
                logger.warning(
                    "Model '%s' failed to load (%s). Falling back to 'buffalo_l'...",
                    model_to_use,
                    e_primary,
                )
                self._app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
                self._app.prepare(ctx_id=-1, det_thresh=0.4, det_size=(640, 640))
                self._current_det_size = (640, 640)
                self._current_det_thresh = 0.4
                self._initialized = True
                logger.info("InsightFace successfully initialized with fallback 'buffalo_l'")
                return True
        except Exception as exc:
            logger.error("Failed to initialize InsightFace engine: %s", exc)
            self._initialized = False
            return False

    def decode_image(self, image_input: Any) -> Optional[np.ndarray]:
        """Converts bytes, base64 str, or file to an OpenCV BGR numpy image."""
        try:
            import cv2

            img_bytes = None
            if isinstance(image_input, np.ndarray):
                return image_input

            if isinstance(image_input, str):
                if "," in image_input:
                    image_input = image_input.split(",", 1)[1]
                img_bytes = base64.b64decode(image_input)

            elif isinstance(image_input, (bytes, bytearray)):
                img_bytes = bytes(image_input)

            elif hasattr(image_input, "read"):
                img_bytes = image_input.read()

            if img_bytes:
                nparr = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    return img
                
                # Robust fallback via PIL
                from PIL import Image
                pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        except Exception as exc:
            logger.error("Failed to decode image input: %s", exc)
        return None

    def extract_face_crop_base64(self, img_bgr: np.ndarray, bbox: List[float], pad_ratio: float = 0.2) -> str:
        """Crops face with padding and encodes to JPEG Base64."""
        try:
            import cv2

            h, w, _ = img_bgr.shape
            x1, y1, x2, y2 = [int(v) for v in bbox]
            bw, bh = x2 - x1, y2 - y1
            pad_x = int(bw * pad_ratio)
            pad_y = int(bh * pad_ratio)

            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(w, x2 + pad_x)
            y2 = min(h, y2 + pad_y)

            crop = img_bgr[y1:y2, x1:x2]
            if crop.size == 0:
                crop = img_bgr

            # Resize to standardized thumbnail size
            crop_resized = cv2.resize(crop, (160, 160))
            _, buf = cv2.imencode(".jpg", crop_resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return base64.b64encode(buf).decode("utf-8")
        except Exception as exc:
            logger.error("Failed to generate face crop: %s", exc)
            return ""

    def process_frame(self, image_input: Any) -> List[Dict[str, Any]]:
        """
        Detects all faces in frame and extracts their 512-dim normalized embeddings.
        Returns a list of dicts:
        [
            {
                "bbox": [x1, y1, x2, y2],
                "confidence": 0.98,
                "embedding": [0.034, -0.012, ...], # 512 floats
                "thumbnail_b64": "..."
            }
        ]
        """
        img_bgr = self.decode_image(image_input)
        if img_bgr is None:
            return []

        if not self.initialize():
            logger.error("FaceEngine not initialized; returning empty faces")
            return []

        try:
            h, w = img_bgr.shape[:2]
            # Primary candidate scales based on image dimensions
            candidate_scales = []
            if max(h, w) <= 360:
                candidate_scales = [(320, 320), (160, 160), (640, 640)]
            elif max(h, w) >= 1200:
                candidate_scales = [(640, 640), (960, 960), (320, 320)]
            else:
                candidate_scales = [(640, 640), (320, 320), (480, 480)]

            faces = []
            for det_sz in candidate_scales:
                self._ensure_det_params(det_size=det_sz, det_thresh=0.4)
                detected = self._app.get(img_bgr)
                if detected:
                    faces = detected
                    break

            # If still no faces and image is small, try upscaling
            if not faces and max(h, w) < 400:
                try:
                    import cv2
                    factor = 480.0 / max(h, w)
                    upscaled = cv2.resize(img_bgr, (int(w * factor), int(h * factor)), interpolation=cv2.INTER_CUBIC)
                    self._ensure_det_params(det_size=(480, 480), det_thresh=0.35)
                    detected = self._app.get(upscaled)
                    if detected:
                        faces = detected
                        img_bgr = upscaled  # use upscaled for bbox & thumbnail
                except Exception as up_err:
                    logger.debug("Upscaled detection failed: %s", up_err)

            results = []
            for face in faces:
                normed_emb = getattr(face, "normed_embedding", None)
                if normed_emb is None and hasattr(face, "embedding"):
                    norm = np.linalg.norm(face.embedding)
                    normed_emb = face.embedding / (norm + 1e-9)

                if normed_emb is None:
                    continue

                bbox = face.bbox.tolist()
                det_score = float(getattr(face, "det_score", 0.95))
                thumbnail_b64 = self.extract_face_crop_base64(img_bgr, bbox)

                results.append({
                    "bbox": bbox,
                    "confidence": round(det_score, 4),
                    "embedding": normed_emb.tolist(),
                    "thumbnail_b64": thumbnail_b64,
                })
            return results
        except Exception as exc:
            logger.error("Error processing faces in frame: %s", exc)
            return []


face_engine = FaceEngine(model_name="antelopev2")

