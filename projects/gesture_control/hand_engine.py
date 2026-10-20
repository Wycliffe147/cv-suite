"""
projects/gesture_control/hand_engine.py
----------------------------------------
MediaPipe Hand Landmarker wrapper for 21 3D joint tracking.
Provides high-level geometric analyses:
- Finger extension states (Thumb, Index, Middle, Ring, Pinky)
- Pinch detection (Thumb-to-Index distance)
- Palm position and motion tracking
"""

import math
from pathlib import Path
from typing import List, Optional, Tuple, Any
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision

MODEL_PATH = Path(__file__).parents[2] / "data" / "models" / "hand_landmarker.task"

# MediaPipe landmark indices
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20


class HandData:
    def __init__(self, landmarks: List[Any], img_w: int, img_h: int) -> None:
        self.landmarks = landmarks
        self.w = img_w
        self.h = img_h

        # Convert to pixel coordinates
        self.pts = [
            (lm.x * img_w, lm.y * img_h, lm.z * img_w)
            for lm in landmarks
        ]

    def dist(self, i: int, j: int) -> float:
        """Euclidean distance between two landmarks."""
        p1, p2 = self.pts[i], self.pts[j]
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

    def is_extended(self, tip_idx: int, pip_idx: int, mcp_idx: int) -> bool:
        """True if fingertip is significantly further from wrist than its PIP/MCP."""
        wrist = self.pts[WRIST]
        tip = self.pts[tip_idx]
        pip = self.pts[pip_idx]
        d_tip = math.sqrt((tip[0] - wrist[0])**2 + (tip[1] - wrist[1])**2)
        d_pip = math.sqrt((pip[0] - wrist[0])**2 + (pip[1] - wrist[1])**2)
        return d_tip > d_pip * 1.15

    @property
    def thumb_extended(self) -> bool:
        # Check thumb tip distance from index MCP
        d_tip = self.dist(THUMB_TIP, INDEX_MCP)
        d_ip = self.dist(THUMB_IP, INDEX_MCP)
        return d_tip > d_ip * 1.15

    @property
    def index_extended(self) -> bool:
        return self.is_extended(INDEX_TIP, INDEX_PIP, INDEX_MCP)

    @property
    def middle_extended(self) -> bool:
        return self.is_extended(MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP)

    @property
    def ring_extended(self) -> bool:
        return self.is_extended(RING_TIP, RING_PIP, RING_MCP)

    @property
    def pinky_extended(self) -> bool:
        return self.is_extended(PINKY_TIP, PINKY_PIP, PINKY_MCP)

    @property
    def pinch_distance(self) -> float:
        """Distance between thumb tip and index tip in pixels."""
        return self.dist(THUMB_TIP, INDEX_TIP)

    @property
    def is_pointing(self) -> bool:
        """True if index finger is prominently pointing/raised above middle, ring, pinky."""
        wrist = self.pts[WRIST]
        d_index = math.sqrt((self.pts[INDEX_TIP][0] - wrist[0])**2 + (self.pts[INDEX_TIP][1] - wrist[1])**2)
        d_middle = math.sqrt((self.pts[MIDDLE_TIP][0] - wrist[0])**2 + (self.pts[MIDDLE_TIP][1] - wrist[1])**2)
        d_ring = math.sqrt((self.pts[RING_TIP][0] - wrist[0])**2 + (self.pts[RING_TIP][1] - wrist[1])**2)
        d_pinky = math.sqrt((self.pts[PINKY_TIP][0] - wrist[0])**2 + (self.pts[PINKY_TIP][1] - wrist[1])**2)
        
        # Index must be extended and noticeably longer from wrist than middle, ring, pinky
        return self.index_extended and (d_index > d_middle * 1.15) and (d_index > d_ring * 1.2) and (d_index > d_pinky * 1.2)

    @property
    def is_pinching(self) -> bool:
        """True if thumb tip and index tip are touching / close."""
        palm_size = self.dist(WRIST, MIDDLE_MCP)
        return self.pinch_distance < (palm_size * 0.32)

    @property
    def palm_center(self) -> Tuple[float, float]:
        """Approximate center of the palm."""
        p0, p5, p17 = self.pts[WRIST], self.pts[INDEX_MCP], self.pts[PINKY_MCP]
        return ((p0[0] + p5[0] + p17[0]) / 3.0, (p0[1] + p5[1] + p17[1]) / 3.0)


class HandEngine:
    def __init__(self, model_path: Path = MODEL_PATH, max_hands: int = 1) -> None:
        if not model_path.exists():
            raise FileNotFoundError(f"Hand model not found: {model_path}")

        options = mp_vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp_vision.RunningMode.IMAGE,
            num_hands=max_hands,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self._landmarker = mp_vision.HandLandmarker.create_from_options(options)

    def process(self, frame: np.ndarray) -> Optional[HandData]:
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = self._landmarker.detect(mp_img)

        if not res.hand_landmarks or len(res.hand_landmarks) == 0:
            return None

        return HandData(res.hand_landmarks[0], img_w=w, img_h=h)

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "HandEngine":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
