"""
projects/privacy_guard/face_db.py
----------------------------------
Face embedding database & recognizer wrapper using OpenCV's SFace (FaceRecognizerSF).
Stores 128-D / 512-D L2-normalized feature embeddings in SQLite.
"""

import sqlite3
from pathlib import Path
from typing import List, Tuple, Optional
import cv2
import numpy as np

# Suppress harmless OpenCV graph engine info warnings
cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)

DB_PATH = Path(__file__).parents[2] / "data" / "face_db" / "enrolled_faces.db"
SFACE_MODEL = Path(__file__).parents[2] / "data" / "models" / "face_recognition_sface.onnx"
YUNET_MODEL = Path(__file__).parents[2] / "data" / "models" / "face_detection_yunet.onnx"


def enhance_crop(crop_bgr: np.ndarray) -> np.ndarray:
    """Apply CLAHE contrast enhancement to normalize shadows and varying ambient lighting."""
    lab = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)


class FaceRecognizer:
    def __init__(
        self,
        sface_model_path: Path = SFACE_MODEL,
        yunet_model_path: Path = YUNET_MODEL,
        db_path: Path = DB_PATH,
        cosine_threshold: float = 0.42,  # 0.42 accommodates natural lighting and slight off-angles
    ) -> None:
        self.db_path = db_path
        self.cosine_threshold = cosine_threshold

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        if not sface_model_path.exists():
            raise FileNotFoundError(f"SFace model not found at {sface_model_path}")
        if not yunet_model_path.exists():
            raise FileNotFoundError(f"YuNet model not found at {yunet_model_path}")

        self.recognizer = cv2.FaceRecognizerSF.create(str(sface_model_path), "")
        self.detector = cv2.FaceDetectorYN.create(
            str(yunet_model_path), "", (320, 320), score_threshold=0.6, nms_threshold=0.3
        )

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS enrolled_faces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def extract_faces(self, frame: np.ndarray) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Detect all faces in a BGR frame and extract their embeddings.
        Returns a list of tuples: (bounding_box_and_landmarks, embedding_vector)
        """
        h, w = frame.shape[:2]
        self.detector.setInputSize((w, h))
        _, detected_faces = self.detector.detect(frame)

        if detected_faces is None or len(detected_faces) == 0:
            return []

        results = []
        for face in detected_faces:
            # Align face crop using 5 landmarks detected by YuNet
            aligned_face = self.recognizer.alignCrop(frame, face)
            # Apply CLAHE contrast enhancement for lighting invariance
            enhanced_face = enhance_crop(aligned_face)
            # Extract normalized feature vector
            feature = self.recognizer.feature(enhanced_face)
            results.append((face, feature))

        return results

    def enroll(self, name: str, frame: np.ndarray) -> bool:
        """Enroll a face from a frame under `name`."""
        faces = self.extract_faces(frame)
        if len(faces) != 1:
            # For clean enrollment, exactly 1 face should be in frame
            return False

        _, feature = faces[0]
        feature_bytes = feature.tobytes()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO enrolled_faces (name, embedding) VALUES (?, ?)",
                (name, feature_bytes)
            )
            conn.commit()
        return True

    def identify(self, feature: np.ndarray) -> Tuple[Optional[str], float]:
        """
        Compare a feature embedding against all enrolled faces in the DB.
        Returns (matched_name, distance). If distance <= threshold, matched_name is not None.
        (Lower distance = higher similarity for cosine distance in SFace)
        """
        best_name = None
        best_score = float("inf")

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT name, embedding FROM enrolled_faces").fetchall()

        if not rows:
            return None, float("inf")

        for name, emb_bytes in rows:
            enrolled_feat = np.frombuffer(emb_bytes, dtype=np.float32).reshape(1, -1)
            # Match score using Cosine distance (cv2.FaceRecognizerSF_FR_COSINE)
            # SFace cosine distance: <= 0.363 is a confirmed match
            distance = self.recognizer.match(feature, enrolled_feat, cv2.FaceRecognizerSF_FR_COSINE)
            if distance < best_score:
                best_score = distance
                if distance <= self.cosine_threshold:
                    best_name = name

        return best_name, best_score

    def list_enrolled(self) -> List[Tuple[str, int]]:
        """Return list of (name, count) of enrolled faces."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT name, count(*) FROM enrolled_faces GROUP BY name"
            ).fetchall()
        return rows
