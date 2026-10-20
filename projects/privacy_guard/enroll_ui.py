"""
projects/privacy_guard/enroll_ui.py
------------------------------------
Interactive, guided visual face enrollment (similar to Android / iOS Face ID).
Features:
- Live OpenCV viewfinder with circular face target guide
- Real-time lighting quality estimation & CLAHE enhancement
- Guided multi-pose capture: Center -> Left -> Right -> Down -> Up
- Visual progress ring / step indicators
"""

import math
import time
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np

from projects.privacy_guard.face_db import FaceRecognizer
from core import load_config, DutyCycleCamera, FaceEngine, HeadPose

# Step definitions: target head poses
POSES = [
    {"name": "Look Straight Ahead", "check": lambda p: abs(p.yaw) < 12 and abs(p.pitch) < 12},
    {"name": "Turn Slightly Left",   "check": lambda p: p.yaw < -15},
    {"name": "Turn Slightly Right",  "check": lambda p: p.yaw > 15},
    {"name": "Tilt Slightly Down",   "check": lambda p: p.pitch > 15},
    {"name": "Tilt Slightly Up",     "check": lambda p: p.pitch < -12},
]


def check_lighting(gray_crop: np.ndarray) -> Tuple[str, Tuple[int, int, int]]:
    """Estimate lighting quality from face crop."""
    brightness = np.mean(gray_crop)
    if brightness < 45:
        return "Too Dark (Need Light)", (0, 0, 255)  # Red
    elif brightness > 215:
        return "Too Bright / Washed Out", (0, 0, 255)  # Red
    elif brightness < 65:
        return "Dim Lighting", (0, 165, 255)  # Orange
    return "Lighting Good ✓", (0, 255, 0)  # Green


def apply_clahe(bgr_image: np.ndarray) -> np.ndarray:
    """Enhance lighting contrast using CLAHE in LAB color space."""
    lab = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    limg = cv2.merge((cl, a, b))
    return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)


def run_interactive_enrollment(name: str) -> bool:
    cfg = load_config()
    cam_device = cfg["camera"]["device"]
    
    cap = cv2.VideoCapture(cam_device)
    if not cap.isOpened():
        print(f"Error: Could not open camera {cam_device}")
        return False

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    recognizer = FaceRecognizer()
    face_engine = FaceEngine(
        model_path=cfg["models"]["face_landmarker"],
        max_faces=1,
    )

    current_step = 0
    samples_per_step = 2
    step_samples = 0
    enrolled_count = 0
    hold_start: Optional[float] = None

    window_name = f"cv-suite · Face Enrollment: {name}"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    print(f"\n📸 Starting interactive visual enrollment for '{name}'...")
    print("Follow the on-screen instructions in the camera window.\n")

    try:
        while current_step < len(POSES):
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            frame = cv2.flip(frame, 1)  # Mirror view for natural interaction
            h, w = frame.shape[:2]
            cx, cy = w // 2, h // 2
            oval_rx, oval_ry = 130, 170

            # Process head pose with FaceEngine
            event = face_engine.process(frame)
            
            # Draw semi-transparent dark vignette outside face oval
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.ellipse(mask, (cx, cy), (oval_rx, oval_ry), 0, 0, 360, 255, -1)
            overlay = frame.copy()
            overlay[mask == 0] = (overlay[mask == 0] * 0.45).astype(np.uint8)
            display = overlay

            target_pose = POSES[current_step]
            step_text = f"Step {current_step + 1}/{len(POSES)}: {target_pose['name']}"

            # Lighting analysis
            face_roi_gray = cv2.cvtColor(frame[max(0, cy - oval_ry):min(h, cy + oval_ry),
                                               max(0, cx - oval_rx):min(w, cx + oval_rx)], cv2.COLOR_BGR2GRAY)
            light_label, light_color = check_lighting(face_roi_gray)

            # Pose feedback & enrollment trigger
            target_hit = False
            pose_str = "Position your face in the oval"
            guide_color = (180, 180, 180)  # Default grey

            if event.is_present and event.head_pose:
                p = event.head_pose
                # Note: mirrored frame flips yaw display
                corrected_pose = HeadPose(yaw=-p.yaw, pitch=p.pitch, roll=p.roll)
                pose_str = f"Yaw: {corrected_pose.yaw:+.0f}° | Pitch: {corrected_pose.pitch:+.0f}°"

                if target_pose["check"](corrected_pose):
                    target_hit = True
                    guide_color = (0, 255, 0)  # Green

                    if hold_start is None:
                        hold_start = time.monotonic()
                    
                    elapsed = time.monotonic() - hold_start
                    
                    # Capture after steady hold of 0.6 seconds
                    if elapsed >= 0.6:
                        # Extract and enroll with CLAHE-enhanced contrast
                        enhanced_frame = apply_clahe(frame)
                        faces = recognizer.extract_faces(enhanced_frame)
                        if len(faces) == 1:
                            recognizer.enroll(name, enhanced_frame)
                            step_samples += 1
                            enrolled_count += 1
                            hold_start = None

                            if step_samples >= samples_per_step:
                                current_step += 1
                                step_samples = 0
                else:
                    hold_start = None
                    guide_color = (0, 180, 255)  # Orange: adjust angle
            else:
                hold_start = None
                guide_color = (0, 0, 255)  # Red: no face

            # Draw target oval guide
            cv2.ellipse(display, (cx, cy), (oval_rx, oval_ry), 0, 0, 360, guide_color, 3)

            # Draw UI header card
            cv2.rectangle(display, (0, 0), (w, 80), (25, 25, 25), -1)
            cv2.putText(display, f"Enrolling: {name}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(display, step_text, (20, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)

            # Draw lighting & pose footer card
            cv2.rectangle(display, (0, h - 70), (w, h), (25, 25, 25), -1)
            cv2.putText(display, f"Light: {light_label}", (20, h - 42), cv2.FONT_HERSHEY_SIMPLEX, 0.55, light_color, 2)
            cv2.putText(display, pose_str, (20, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            # Progress indicators on right
            for i, p_info in enumerate(POSES):
                dot_y = 110 + i * 28
                dot_color = (0, 255, 0) if i < current_step else ((0, 255, 255) if i == current_step else (100, 100, 100))
                cv2.circle(display, (w - 25, dot_y), 7, dot_color, -1)
                cv2.circle(display, (w - 25, dot_y), 7, (255, 255, 255), 1)

            # Press Q or ESC to cancel
            cv2.imshow(window_name, display)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord('q')):
                print("\nEnrollment cancelled by user.")
                return False

        # Success screen
        ret, frame = cap.read()
        if ret and frame is not None:
            frame = cv2.flip(frame, 1)
            cv2.rectangle(frame, (0, 0), (w, h), (0, 0, 0), -1)
            cv2.putText(frame, "✓ Enrollment Complete!", (w // 2 - 180, h // 2 - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            cv2.putText(frame, f"Saved {enrolled_count} multi-angle samples for {name}",
                        (w // 2 - 210, h // 2 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.imshow(window_name, frame)
            cv2.waitKey(2000)

        print(f"\n🎉 Successfully enrolled {enrolled_count} multi-angle samples for '{name}' with CLAHE lighting normalization!\n")
        return True

    finally:
        cap.release()
        face_engine.close()
        cv2.destroyAllWindows()
