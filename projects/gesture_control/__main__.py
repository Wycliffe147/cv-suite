"""
projects/gesture_control/__main__.py
-------------------------------------
CLI runner for Multi-Modal Intent-Gated Hand & Face Controller.
Usage:
  python -m projects.gesture_control          # Runs in terminal daemon mode
  python -m projects.gesture_control --hud    # Runs with live interactive camera HUD
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

import argparse
import sys
import time
import cv2
import numpy as np

from core import load_config, DutyCycleCamera, FaceEngine
from projects.gesture_control.hand_engine import HandEngine
from projects.gesture_control.gestures import GestureClassifier, GestureType

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
CLEAR = "\033[2K\r"


def draw_hud(frame: np.ndarray, hand_data, face_event, gesture_event, classifier, last_action: str) -> np.ndarray:
    display = cv2.flip(frame, 1)  # Mirror view
    h, w = display.shape[:2]

    # Intent Gate Banner
    now = time.monotonic()
    
    if classifier.is_intent_latched:
        # Check if looking at screen or in grace buffer
        if face_event.is_present and face_event.is_focused:
            banner_color = (0, 180, 0)  # Green
            banner_text = "INTENT GATE: ACTIVE (Eyes on Screen)"
        else:
            time_away = now - classifier.last_focused_time
            remaining = max(0.0, classifier.intent_release_delay - time_away)
            banner_color = (0, 165, 255)  # Orange
            banner_text = f"INTENT GATE: ACTIVE (Grace Buffer: {remaining:.1f}s)"
    elif classifier.focused_since is not None:
        focus_duration = now - classifier.focused_since
        remaining = max(0.0, classifier.intent_focus_hold - focus_duration)
        banner_color = (0, 215, 255)  # Yellow
        banner_text = f"INTENT GATE: LOCKING IN... {remaining:.1f}s"
    elif face_event.is_present:
        banner_color = (0, 100, 255)  # Red-Orange
        banner_text = "INTENT GATE: LOCKED (Looking Away - Gestures Ignored)"
    else:
        banner_color = (0, 0, 200)  # Red
        banner_text = "INTENT GATE: LOCKED (No Face Present)"

    cv2.rectangle(display, (0, 0), (w, 50), banner_color, -1)
    cv2.putText(display, banner_text, (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

    # Draw Hand Skeleton if detected
    if hand_data:
        # Mirrored x coordinates
        for x, y, _ in hand_data.pts:
            mx = int(w - x)
            my = int(y)
            cv2.circle(display, (mx, my), 5, (0, 255, 255), -1)

        # Draw pinch line or pointing reticle
        p_thumb = hand_data.pts[4]
        p_index = hand_data.pts[8]
        tx, ty = int(w - p_thumb[0]), int(p_thumb[1])
        ix, iy = int(w - p_index[0]), int(p_index[1])

        if gesture_event.gesture in (GestureType.AIR_MOUSE, GestureType.AIR_CLICK):
            reticle_color = (0, 0, 255) if gesture_event.gesture == GestureType.AIR_CLICK else (0, 255, 0)
            cv2.circle(display, (ix, iy), 18, reticle_color, 2)
            cv2.line(display, (ix - 24, iy), (ix + 24, iy), reticle_color, 1)
            cv2.line(display, (ix, iy - 24), (ix, iy + 24), reticle_color, 1)
        else:
            line_color = (0, 255, 0) if hand_data.is_pinching else (200, 200, 200)
            cv2.line(display, (tx, ty), (ix, iy), line_color, 2)

    # Bottom status card
    cv2.rectangle(display, (0, h - 60), (w, h), (25, 25, 25), -1)
    gesture_name = gesture_event.gesture.name if gesture_event.gesture != GestureType.NONE else "Waiting for gesture..."
    cv2.putText(display, f"Gesture: {gesture_name}", (20, h - 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    if last_action:
        cv2.putText(display, f"Action: {last_action}", (20, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

    return display


def parse_args():
    parser = argparse.ArgumentParser(description="Multi-Modal Intent-Gated Hand & Face Controller")
    parser.add_argument("--hud", action="store_true", help="Display visual camera HUD window")
    parser.add_argument("--fps", type=float, default=15.0, help="Target polling rate (default: 15.0 FPS)")
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = load_config()

    cap = cv2.VideoCapture(cfg["camera"]["device"])
    if not cap.isOpened():
        print(f"{RED}✗ Camera /dev/video{cfg['camera']['device']} not available.{RESET}")
        return 1

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    face_cfg = cfg["face"]
    pose_cfg = cfg["head_pose"]

    face_engine = FaceEngine(
        model_path=cfg["models"]["face_landmarker"],
        max_faces=1,
        yaw_threshold=pose_cfg["yaw_threshold"],
        pitch_up_threshold=pose_cfg.get("pitch_up_threshold", 25.0),
        pitch_down_threshold=pose_cfg.get("pitch_down_threshold", 40.0),
    )
    hand_engine = HandEngine()
    classifier = GestureClassifier()

    print(f"\n{BOLD}cv-suite · Intent-Gated Gesture Controller 🖐️👀{RESET}")
    print(f"  ☝️ Point Index:     Air Mouse Cursor (Move index to steer)")
    print(f"  👌 Pinch While Aim: Left Click (Thumb touches index)")
    print(f"  🖐️ Open Palm:       Pause Media")
    print(f"  👍 Thumbs Up:       Resume Media")
    print(f"  ✌️ Victory (V):     Next Track")
    print(f"  👌 Pinch + Drag:    Volume Dial (+/- 10%)")
    print(f"  👁️ Intent Gate:     Gestures only work after 1.0s steady focus on screen!")
    print(f"\n  Press {BOLD}Ctrl+C{RESET} (or Q in HUD) to stop.\n")

    last_action_str = ""
    poll_sleep = 1.0 / args.fps

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            # Run Face Engine (Check Intent) & Hand Engine
            face_event = face_engine.process(frame)
            hand_data = hand_engine.process(frame)
            gesture_event = classifier.classify(hand_data, face_event)

            if gesture_event.action_executed:
                last_action_str = gesture_event.action_executed

            if args.hud:
                hud_frame = draw_hud(frame, hand_data, face_event, gesture_event, classifier, last_action_str)
                cv2.imshow("cv-suite · Intent-Gated Controller", hud_frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord('q')):
                    break
            else:
                if classifier.is_intent_latched:
                    if face_event.is_present and face_event.is_focused:
                        intent_badge = f"{GREEN}👁️ INTENT ACTIVE{RESET}"
                    else:
                        time_away = time.monotonic() - classifier.last_focused_time
                        rem = max(0.0, classifier.intent_release_delay - time_away)
                        intent_badge = f"{YELLOW}⏳ GRACE ({rem:.1f}s){RESET}"
                else:
                    intent_badge = f"{RED}🔒 LOCKED{RESET}"
                gest_name = gesture_event.gesture.name if gesture_event.gesture != GestureType.NONE else "NONE"
                act_str = f"  {BOLD}➜ {last_action_str}{RESET}" if last_action_str else ""
                print(f"{CLEAR}{intent_badge} | Gesture: {gest_name:<12}{act_str}", end="", flush=True)

            time.sleep(poll_sleep)

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        face_engine.close()
        hand_engine.close()
        cv2.destroyAllWindows()
        print(f"\n\n{BOLD}Gesture controller stopped.{RESET}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
