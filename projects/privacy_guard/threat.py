"""
projects/privacy_guard/threat.py
---------------------------------
Threat detection engine for Shoulder Surfer:
- Tracks presence of enrolled vs. unrecognized faces over time
- Triggers graduated responses:
  - Level 1: Conceal screen (minimize/empty workspace) if unknown face lingers > 1.5s
  - Level 2: Lock workstation if unknown face persists > 4.0s
- Logs silent snapshots of the threat
"""

import time
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np

from projects.privacy_guard.face_db import FaceRecognizer
from projects.privacy_guard import actions


@dataclass
class ThreatReport:
    total_faces: int
    recognized_names: List[str]
    unknown_count: int
    threat_duration_sec: float
    level: int  # 0: Safe, 1: Concealed, 2: Locked
    action_taken: Optional[str] = None


class ThreatDetector:
    def __init__(
        self,
        recognizer: FaceRecognizer,
        level1_delay_sec: float = 1.5,
        level2_delay_sec: float = 4.0,
    ) -> None:
        self.recognizer = recognizer
        self.level1_delay = level1_delay_sec
        self.level2_delay = level2_delay_sec

        self.threat_start_time: Optional[float] = None
        self.level1_triggered: bool = False
        self.level2_triggered: bool = False
        self.last_snapshot_time: float = 0.0

    def evaluate(self, frame: np.ndarray) -> ThreatReport:
        now = time.monotonic()
        faces = self.recognizer.extract_faces(frame)

        recognized_names = []
        unknown_count = 0

        for _, feature in faces:
            name, score = self.recognizer.identify(feature)
            if name is not None:
                recognized_names.append(name)
            else:
                unknown_count += 1

        total_faces = len(faces)
        action_taken = None
        level = 0

        # Threat condition: An unknown face is present in frame
        if unknown_count > 0:
            if self.threat_start_time is None:
                self.threat_start_time = now

            threat_duration = now - self.threat_start_time

            # Check Level 2 (Strict Lock)
            if threat_duration >= self.level2_delay and not self.level2_triggered:
                self.level2_triggered = True
                level = 2
                actions.lock_screen()
                action_taken = f"🚨 LEVEL 2: WORKSTATION LOCKED (Intruder lingered {threat_duration:.1f}s)"
                
                # Take intruder snapshot
                snap_path = actions.save_snapshot(frame, tag="intruder_lock")
                if snap_path:
                    action_taken += f" [Snapshot saved: {snap_path.name}]"

            # Check Level 1 (Conceal screen)
            elif threat_duration >= self.level1_delay and not self.level1_triggered:
                self.level1_triggered = True
                level = 1
                actions.conceal_screen()
                action_taken = f"🛡️ LEVEL 1: SCREEN CONCEALED (Unknown face detected {threat_duration:.1f}s)"

                # Take subtle intruder snapshot
                actions.save_snapshot(frame, tag="intruder_alert")
            elif self.level2_triggered:
                level = 2
            elif self.level1_triggered:
                level = 1

        else:
            # Threat cleared
            threat_duration = 0.0
            self.threat_start_time = None
            self.level1_triggered = False
            self.level2_triggered = False

        return ThreatReport(
            total_faces=total_faces,
            recognized_names=recognized_names,
            unknown_count=unknown_count,
            threat_duration_sec=threat_duration,
            level=level,
            action_taken=action_taken,
        )
