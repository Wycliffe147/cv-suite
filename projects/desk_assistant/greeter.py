"""
projects/desk_assistant/greeter.py
-----------------------------------
Greeting logic and cooldown management:
- Greets recognized contacts with contextual messages (Morning/Afternoon/Evening)
- Cooldown period per person (default: 30 minutes) to avoid repetitive chatter
- Handles unknown visitors: alerts owner, announces desk owner away, logs snapshot
"""

import time
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np

from projects.privacy_guard.face_db import FaceRecognizer
from projects.privacy_guard import actions
from projects.truefocus import notifications
from projects.desk_assistant import voice


def get_time_greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    elif hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"


class DeskGreeter:
    def __init__(
        self,
        recognizer: FaceRecognizer,
        cooldown_sec: float = 1800.0,  # 30 minutes between greetings for the same person
        visitor_cooldown_sec: float = 300.0,  # 5 minutes for unknown visitor alerts
    ) -> None:
        self.recognizer = recognizer
        self.cooldown_sec = cooldown_sec
        self.visitor_cooldown_sec = visitor_cooldown_sec

        # Map of person_name -> last_greeted_timestamp
        self.last_greeted: Dict[str, float] = {}
        self.last_visitor_alert: float = 0.0

    def process_frame(self, frame: np.ndarray) -> List[str]:
        """
        Evaluate frame, determine if any greeting or visitor announcement should be triggered.
        Returns a list of actions/announcements performed.
        """
        now = time.monotonic()
        faces = self.recognizer.extract_faces(frame)
        actions_taken = []

        if not faces:
            return actions_taken

        recognized_names = []
        has_unknown = False

        for _, feature in faces:
            name, _ = self.recognizer.identify(feature)
            if name is not None:
                recognized_names.append(name)
            else:
                has_unknown = True

        # 1. Greet recognized contacts
        for name in recognized_names:
            last_time = self.last_greeted.get(name, 0.0)
            if now - last_time >= self.cooldown_sec:
                self.last_greeted[name] = now
                greeting_text = f"{get_time_greeting()}, {name}. Welcome back."
                voice.speak(greeting_text)
                actions_taken.append(f"🎙️ Greeted {name}: '{greeting_text}'")

        # 2. Handle unknown visitors when no recognized owner is with them
        if has_unknown and not recognized_names:
            if now - self.last_visitor_alert >= self.visitor_cooldown_sec:
                self.last_visitor_alert = now
                
                # Desktop notification
                notifications.send_notification(
                    "👤 Desk Visitor Detected",
                    "An unrecognized person approached your workspace.",
                    urgency="normal"
                )

                # Save visitor photo snapshot
                snap = actions.save_snapshot(frame, tag="visitor")
                snap_msg = f" (Snapshot: {snap.name})" if snap else ""

                # Voice announcement to the visitor
                visitor_speech = "Hello. The desk owner is currently away. Your visit has been logged."
                voice.speak(visitor_speech)
                actions_taken.append(f"🔔 Unknown visitor alerted{snap_msg}")

        return actions_taken
