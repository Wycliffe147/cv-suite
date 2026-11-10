"""
daemon.py
---------
Unified background service for cv-suite.

Runs a single duty-cycled camera capture loop and coordinates:
  1. Media Controller (auto pause/play on leaving desk or looking away)
  2. Privacy Guard (shoulder surfer concealment and session lock)
  3. Desk Assistant (voice greeting for enrolled contacts, visitor alerts)
  4. TrueFocus (ergonomic focus time, pomodoro, 20-20-20 alerts)

All features share ONE camera poll and ONE vision pass per cycle, preventing
hardware device contention and minimizing CPU/battery load.

Managed via systemd:
  systemctl --user start cv-suite
  systemctl --user status cv-suite
  systemctl --user stop cv-suite
"""

import argparse
import logging
import os
import signal
import sys
import time
from typing import List, Optional

from core import (
    load_config,
    get_power_state,
    get_sampling_interval,
    DutyCycleCamera,
    FaceEngine,
    FaceEvent,
)

# Feature modules
from projects.media_controller.controller import MediaController
from projects.truefocus.tracker import FocusTracker
from projects.privacy_guard.face_db import FaceRecognizer
from projects.privacy_guard.threat import ThreatDetector
from projects.desk_assistant.greeter import DeskGreeter

# Logging setup (systemd journal captures stdout/stderr with timestamps)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cv-daemon")


class CVDaemon:
    def __init__(self, cfg_override: Optional[dict] = None) -> None:
        self.cfg = cfg_override or load_config()
        self.running = True

        daemon_cfg = self.cfg.get("daemon", {})
        self.enable_media = daemon_cfg.get("enable_media_controller", True)
        self.enable_privacy = daemon_cfg.get("enable_privacy_guard", True)
        self.enable_greeter = daemon_cfg.get("enable_desk_assistant", True)
        self.enable_truefocus = daemon_cfg.get("enable_truefocus", True)

        log.info(
            "Initializing cv-daemon [Media=%s, Privacy=%s, Greeter=%s, TrueFocus=%s]...",
            self.enable_media,
            self.enable_privacy,
            self.enable_greeter,
            self.enable_truefocus,
        )

        # Hardware & Core Vision
        cam_cfg = self.cfg["camera"]
        self.cam = DutyCycleCamera(
            device=cam_cfg["device"],
            width=cam_cfg["width"],
            height=cam_cfg["height"],
        )

        face_cfg = self.cfg["face"]
        pose_cfg = self.cfg["head_pose"]
        self.face_engine = FaceEngine(
            model_path=self.cfg["models"]["face_landmarker"],
            max_faces=face_cfg.get("max_faces", 4),
            min_detection_confidence=face_cfg.get("min_detection_confidence", 0.6),
            min_presence_confidence=face_cfg.get("min_presence_confidence", 0.6),
            min_tracking_confidence=face_cfg.get("min_tracking_confidence", 0.6),
            yaw_threshold=pose_cfg.get("yaw_threshold", 45.0),
            pitch_up_threshold=pose_cfg.get("pitch_up_threshold", 25.0),
            pitch_down_threshold=pose_cfg.get("pitch_down_threshold", 40.0),
        )

        # Shared Face Recognizer (if identity matching is needed)
        self.recognizer: Optional[FaceRecognizer] = None
        if self.enable_privacy or self.enable_greeter:
            priv_cfg = self.cfg.get("privacy_guard", {})
            self.recognizer = FaceRecognizer(
                cosine_threshold=priv_cfg.get("threshold", 0.42)
            )

        # Media Controller
        self.media_ctrl: Optional[MediaController] = None
        if self.enable_media:
            media_cfg = self.cfg.get("media_controller", {})
            self.media_ctrl = MediaController(
                mode=media_cfg.get("mode", "presence"),
                pause_delay=media_cfg.get("pause_delay", 3.0),
                dim_delay=media_cfg.get("dim_delay", 60.0),
                dim_to=media_cfg.get("dim_to", 10),
            )

        # TrueFocus
        self.focus_tracker: Optional[FocusTracker] = None
        if self.enable_truefocus:
            tf_cfg = self.cfg.get("truefocus", {})
            self.focus_tracker = FocusTracker(
                pomodoro_focus_min=tf_cfg.get("pomodoro_min", 50.0),
                away_reset_min=tf_cfg.get("away_reset_min", 5.0),
                eye_strain_min=tf_cfg.get("eye_strain_min", 20.0),
            )

        # Privacy Guard
        self.threat_detector: Optional[ThreatDetector] = None
        if self.enable_privacy and self.recognizer:
            priv_cfg = self.cfg.get("privacy_guard", {})
            self.threat_detector = ThreatDetector(
                recognizer=self.recognizer,
                level1_delay_sec=priv_cfg.get("level1_delay", 1.5),
                level2_delay_sec=priv_cfg.get("level2_delay", 4.0),
            )

        # Desk Greeter
        self.desk_greeter: Optional[DeskGreeter] = None
        if self.enable_greeter and self.recognizer:
            desk_cfg = self.cfg.get("desk_assistant", {})
            self.desk_greeter = DeskGreeter(
                recognizer=self.recognizer,
                cooldown_sec=desk_cfg.get("cooldown_min", 30.0) * 60.0,
                visitor_cooldown_sec=desk_cfg.get("visitor_cooldown_min", 5.0) * 60.0,
            )

        self._last_power_state_battery: Optional[bool] = None
        log.info("cv-daemon ready. Monitoring camera on /dev/video%s", self.cam.device)

    def start(self) -> None:
        if not self.cam.is_available():
            log.error("Camera device %s is unavailable. Exiting.", self.cam.device)
            return

        while self.running:
            power = get_power_state()
            if self._last_power_state_battery != power.on_battery:
                self._last_power_state_battery = power.on_battery
                source = "Battery" if power.on_battery else "AC Power"
                log.info("Power source changed to %s (interval adapted)", source)

            interval = get_sampling_interval(
                ac_interval=self.cfg["sampling"]["ac_interval"],
                dc_interval=self.cfg["sampling"]["dc_interval"],
            )

            frame = self.cam.grab_frame()
            if frame is None:
                time.sleep(interval)
                continue

            # Core vision pass (Landmarks + Head Pose)
            event: FaceEvent = self.face_engine.process(frame)

            # 1. Media Controller tick
            if self.media_ctrl:
                status = self.media_ctrl.tick(event)
                if status.action:
                    log.info("[Media] %s", status.action)

            # 2. TrueFocus tick
            if self.focus_tracker:
                snap = self.focus_tracker.tick(event)
                if snap.message:
                    log.info("[TrueFocus] %s", snap.message)

            # 3. Identity-based features (Privacy Guard + Desk Assistant)
            if (self.threat_detector or self.desk_greeter) and self.recognizer:
                recognized_names: List[str] = []
                unknown_count = 0

                # Only run face recognition if at least one face is present
                if event.is_present:
                    faces = self.recognizer.extract_faces(frame)
                    for _, feature in faces:
                        name, _ = self.recognizer.identify(feature)
                        if name is not None:
                            recognized_names.append(name)
                        else:
                            unknown_count += 1

                # Privacy Guard
                if self.threat_detector:
                    report = self.threat_detector.evaluate(
                        frame,
                        recognized_names=recognized_names,
                        unknown_count=unknown_count,
                    )
                    if report.action_taken:
                        log.warning("[PrivacyGuard] %s", report.action_taken)

                # Desk Greeter
                if self.desk_greeter:
                    has_unknown = unknown_count > 0
                    actions = self.desk_greeter.process_frame(
                        frame,
                        recognized_names=recognized_names,
                        has_unknown=has_unknown,
                    )
                    for act in actions:
                        log.info("[DeskAssistant] %s", act)

            time.sleep(interval)

    def stop(self) -> None:
        log.info("cv-daemon shutting down gracefully...")
        self.running = False
        if self.media_ctrl:
            self.media_ctrl.shutdown()
        if self.face_engine:
            self.face_engine.close()
        log.info("cv-daemon stopped.")


def main() -> int:
    parser = argparse.ArgumentParser(description="cv-suite unified background daemon")
    parser.add_argument("--no-media", action="store_true", help="Disable media controller")
    parser.add_argument("--no-privacy", action="store_true", help="Disable privacy guard")
    parser.add_argument("--no-greeter", action="store_true", help="Disable desk assistant")
    parser.add_argument("--no-focus", action="store_true", help="Disable truefocus tracker")
    args = parser.parse_args()

    cfg = load_config()
    daemon_cfg = cfg.setdefault("daemon", {})
    if args.no_media:
        daemon_cfg["enable_media_controller"] = False
    if args.no_privacy:
        daemon_cfg["enable_privacy_guard"] = False
    if args.no_greeter:
        daemon_cfg["enable_desk_assistant"] = False
    if args.no_focus:
        daemon_cfg["enable_truefocus"] = False

    daemon = CVDaemon(cfg_override=cfg)

    def _sig_handler(sig, frame):
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    try:
        daemon.start()
    except Exception as e:
        log.exception("Unexpected error in cv-daemon: %s", e)
        daemon.stop()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
