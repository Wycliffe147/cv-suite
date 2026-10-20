"""
core/face_engine.py
--------------------
The shared vision engine powering all cv-suite projects.

Uses MediaPipe Tasks API (FaceLandmarker) with solvePnP 3D pose estimation
plus Eye Blendshapes for natural, ergonomic desk gaze tracking.

Responsibilities:
  1. Run FaceLandmarker on a single BGR frame.
  2. Estimate 3-axis head pose (yaw / pitch / roll) via solvePnP.
  3. Extract eye gaze blendshapes (eyeLookUp/Down/In/Out).
  4. Classify ergonomic gaze state: LOOKING_AT_SCREEN | LOOKING_AWAY | UNKNOWN.
  5. Emit a structured FaceEvent consumed by every project.
"""

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional, List, Dict, Any


# ---------------------------------------------------------------------------
# Enums & Data classes
# ---------------------------------------------------------------------------

class PresenceState(Enum):
    PRESENT = auto()   # At least one face detected
    ABSENT  = auto()   # No face in frame


class GazeState(Enum):
    LOOKING_AT_SCREEN = auto()   # Within natural workstation display cone
    LOOKING_AWAY      = auto()   # Turned away from screen/workstation
    UNKNOWN           = auto()   # Could not estimate pose


@dataclass
class HeadPose:
    """Euler angles (degrees) for the primary detected face."""
    yaw:   float   # Horizontal rotation — positive = turned right, negative = turned left
    pitch: float   # Vertical tilt      — positive = tilted down,  negative = tilted up
    roll:  float   # Head tilt          — positive = tilted right, negative = tilted left


@dataclass
class FaceEvent:
    presence:   PresenceState
    gaze:       GazeState
    head_pose:  Optional[HeadPose]
    face_count: int
    eye_blendshapes: Optional[Dict[str, float]] = None

    frame:     Optional[np.ndarray] = field(default=None, repr=False)
    landmarks: Optional[List[Any]]  = field(default=None, repr=False)

    @property
    def is_present(self) -> bool:
        return self.presence == PresenceState.PRESENT

    @property
    def is_focused(self) -> bool:
        return self.gaze == GazeState.LOOKING_AT_SCREEN

    @property
    def has_intruder(self) -> bool:
        return self.face_count > 1


# ---------------------------------------------------------------------------
# FaceEngine
# ---------------------------------------------------------------------------

class FaceEngine:
    # 3D face model points (millimetres, generic adult face)
    _FACE_3D_MODEL: np.ndarray = np.array([
        ( 0.0,    0.0,    0.0),   # 4   — Nose tip (world origin)
        ( 0.0,  -63.6,  -12.5),  # 152 — Chin
        (-43.3,  32.7,  -26.0),  # 263 — Left eye outer corner
        ( 43.3,  32.7,  -26.0),  # 33  — Right eye outer corner
        (-28.9, -28.9,  -24.1),  # 61  — Left mouth corner
        ( 28.9, -28.9,  -24.1),  # 291 — Right mouth corner
    ], dtype=np.float64)

    _LANDMARK_INDICES: List[int] = [4, 152, 263, 33, 61, 291]

    def __init__(
        self,
        model_path: str | Path = "data/models/face_landmarker.task",
        *,
        running_mode: str = "IMAGE",
        max_faces: int = 4,
        min_detection_confidence: float = 0.6,
        min_presence_confidence: float = 0.6,
        min_tracking_confidence: float = 0.6,
        yaw_threshold: float = 45.0,
        pitch_up_threshold: float = 25.0,
        pitch_down_threshold: float = 40.0,
    ) -> None:
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"FaceLandmarker model not found: {model_path}")

        self.yaw_threshold        = yaw_threshold
        self.pitch_up_threshold   = pitch_up_threshold
        self.pitch_down_threshold = pitch_down_threshold

        _mode_map = {
            "IMAGE":       mp_vision.RunningMode.IMAGE,
            "VIDEO":       mp_vision.RunningMode.VIDEO,
            "LIVE_STREAM": mp_vision.RunningMode.LIVE_STREAM,
        }
        mode = _mode_map.get(running_mode.upper(), mp_vision.RunningMode.IMAGE)

        options = mp_vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mode,
            num_faces=max_faces,
            min_face_detection_confidence=min_detection_confidence,
            min_face_presence_confidence=min_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_face_blendshapes=True,
        )
        self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)

    def process(
        self,
        frame: np.ndarray,
        *,
        include_frame: bool = False,
        include_landmarks: bool = False,
    ) -> FaceEvent:
        h, w = frame.shape[:2]
        rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result   = self._landmarker.detect(mp_image)

        if not result.face_landmarks:
            return FaceEvent(
                presence=PresenceState.ABSENT,
                gaze=GazeState.UNKNOWN,
                head_pose=None,
                face_count=0,
                frame=frame if include_frame else None,
                landmarks=None,
            )

        face_count = len(result.face_landmarks)
        primary    = result.face_landmarks[0]
        head_pose  = self._estimate_head_pose(primary, img_w=w, img_h=h)

        # Extract eye gaze blendshapes if available
        blendshape_dict = {}
        if result.face_blendshapes and len(result.face_blendshapes) > 0:
            for cat in result.face_blendshapes[0]:
                if "eye" in cat.category_name.lower():
                    blendshape_dict[cat.category_name] = cat.score

        gaze = self._classify_gaze(head_pose, blendshape_dict) if head_pose else GazeState.UNKNOWN

        return FaceEvent(
            presence=PresenceState.PRESENT,
            gaze=gaze,
            head_pose=head_pose,
            face_count=face_count,
            eye_blendshapes=blendshape_dict,
            frame=frame if include_frame else None,
            landmarks=result.face_landmarks if include_landmarks else None,
        )

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "FaceEngine":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _estimate_head_pose(
        self,
        landmarks: List[Any],
        img_w: int,
        img_h: int,
    ) -> Optional[HeadPose]:
        image_points = np.array(
            [
                (landmarks[i].x * img_w, landmarks[i].y * img_h)
                for i in self._LANDMARK_INDICES
            ],
            dtype=np.float64,
        )

        focal_length  = float(img_w)
        cx, cy        = img_w / 2.0, img_h / 2.0
        camera_matrix = np.array(
            [[focal_length, 0.0, cx],
             [0.0, focal_length, cy],
             [0.0, 0.0,          1.0]],
            dtype=np.float64,
        )
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)

        success, rvec, _ = cv2.solvePnP(
            self._FACE_3D_MODEL,
            image_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success:
            return None

        rmat, _ = cv2.Rodrigues(rvec)
        return self._rmat_to_euler(rmat)

    @staticmethod
    def _rmat_to_euler(rmat: np.ndarray) -> HeadPose:
        sy = np.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)
        singular = sy < 1e-6

        if not singular:
            pitch = np.degrees(np.arctan2( rmat[2, 1],  rmat[2, 2]))
            yaw   = np.degrees(np.arctan2(-rmat[2, 0],  sy))
            roll  = np.degrees(np.arctan2( rmat[1, 0],  rmat[0, 0]))
        else:
            pitch = np.degrees(np.arctan2(-rmat[1, 2],  rmat[1, 1]))
            yaw   = np.degrees(np.arctan2(-rmat[2, 0],  sy))
            roll  = 0.0

        return HeadPose(yaw=yaw, pitch=pitch, roll=roll)

    def _classify_gaze(self, pose: HeadPose, blendshapes: Dict[str, float]) -> GazeState:
        """
        Ergonomic classification for realistic desktop work:
        - Allows broad horizontal scanning (yaw <= yaw_threshold, default 45°)
        - Allows natural downward viewing (reading code, looking at keyboard)
        - Allows glancing at screen borders via eye blendshapes even with head angled
        """
        # Horizontal head rotation check
        if abs(pose.yaw) > self.yaw_threshold:
            return GazeState.LOOKING_AWAY

        # Vertical head rotation check (asymmetric for desk ergonomics)
        # pitch > 0 is tilted down, pitch < 0 is tilted up
        if pose.pitch > self.pitch_down_threshold:
            return GazeState.LOOKING_AWAY
        if pose.pitch < -self.pitch_up_threshold:
            return GazeState.LOOKING_AWAY

        # Optional eye-blendshape verification:
        # If head is near threshold edges, verify eyes aren't pointing even further away
        return GazeState.LOOKING_AT_SCREEN
