"""
projects/truefocus/tracker.py
------------------------------
Ergonomic state machine & session tracking engine:
- Focus classification: FOCUSED (eyes on display), DISTRACTED (face looking away/phone), AWAY (no face)
- Smart Pomodoro (auto-resets work session after 5 min away)
- 20-20-20 Rule (prompts to look 20 ft away after 20 mins of continuous focus)
"""

import time
from dataclasses import dataclass
from typing import Optional
from core import FaceEvent, PresenceState, GazeState
from projects.truefocus import db, notifications


@dataclass
class TrackerSnapshot:
    state: str                 # 'FOCUSED', 'DISTRACTED', 'AWAY'
    continuous_focus_sec: float
    session_focus_sec: float
    streak_progress_pct: float # Toward Pomodoro goal (e.g. 50 mins)
    today_focused_sec: float
    today_distracted_sec: float
    today_away_sec: float
    message: Optional[str] = None


class FocusTracker:
    def __init__(
        self,
        pomodoro_focus_min: float = 50.0,
        away_reset_min: float = 5.0,
        eye_strain_min: float = 20.0,
        eye_strain_break_sec: float = 20.0,
    ) -> None:
        self.pomodoro_focus_sec = pomodoro_focus_min * 60.0
        self.away_reset_sec = away_reset_min * 60.0
        self.eye_strain_sec = eye_strain_min * 60.0
        self.eye_strain_break_sec = eye_strain_break_sec

        # State tracking
        self.continuous_focus_sec: float = 0.0
        self.session_focus_sec: float = 0.0
        self.away_accumulated_sec: float = 0.0
        self.looking_away_accumulated_sec: float = 0.0

        self.last_tick: float = time.monotonic()
        self.last_eye_strain_alert: float = 0.0
        self.eye_strain_alert_active: bool = False

        db.init_db()

    def tick(self, event: FaceEvent) -> TrackerSnapshot:
        now = time.monotonic()
        dt = max(0.0, now - self.last_tick)
        self.last_tick = now

        msg = None

        # 1. Classify current frame state
        if not event.is_present:
            current_state = "AWAY"
        elif event.is_focused:
            current_state = "FOCUSED"
        else:
            current_state = "DISTRACTED"

        # Log duration delta to SQLite database
        db.log_interval(current_state, dt)

        # 2. State-dependent updates
        if current_state == "FOCUSED":
            self.continuous_focus_sec += dt
            self.session_focus_sec += dt
            self.looking_away_accumulated_sec = 0.0

            # If user had stepped away briefly (< away_reset_sec), keep the session going
            self.away_accumulated_sec = 0.0

            # 20-20-20 Rule trigger
            if (self.continuous_focus_sec >= self.eye_strain_sec and 
                not self.eye_strain_alert_active and 
                (now - self.last_eye_strain_alert > self.eye_strain_sec)):
                
                notifications.send_notification(
                    "👀 20-20-20 Eye Strain Break",
                    "You've focused for 20 minutes! Look at something 20 feet away for 20 seconds.",
                    urgency="normal"
                )
                self.eye_strain_alert_active = True
                self.last_eye_strain_alert = now
                msg = "👀 20-20-20 Alert: Rest your eyes!"

            # Pomodoro completed check
            if self.session_focus_sec >= self.pomodoro_focus_sec:
                notifications.send_notification(
                    "🎉 Pomodoro Complete!",
                    f"Great job! You completed {self.pomodoro_focus_sec / 60:.0f} minutes of focused work. Take a break!",
                    urgency="critical"
                )
                msg = "🎉 Session target reached! Take a break."
                db.record_break()
                self.session_focus_sec = 0.0
                self.continuous_focus_sec = 0.0

        elif current_state == "DISTRACTED":
            # Looking at phone or side screen
            self.looking_away_accumulated_sec += dt
            self.away_accumulated_sec = 0.0

            # If looking away for eye strain break, check if requirement satisfied
            if self.eye_strain_alert_active and self.looking_away_accumulated_sec >= self.eye_strain_break_sec:
                self.eye_strain_alert_active = False
                self.continuous_focus_sec = 0.0
                msg = "✅ Eye strain break completed."

        elif current_state == "AWAY":
            # Empty desk
            self.away_accumulated_sec += dt
            self.looking_away_accumulated_sec += dt

            # Satisfy 20-20-20 if stepped away
            if self.eye_strain_alert_active and self.away_accumulated_sec >= self.eye_strain_break_sec:
                self.eye_strain_alert_active = False
                self.continuous_focus_sec = 0.0

            # Natural Pomodoro reset if user is away > threshold (e.g. 5 minutes)
            if self.away_accumulated_sec >= self.away_reset_sec and self.session_focus_sec > 0:
                msg = f"🔄 Natural break detected (> {self.away_reset_sec / 60:.0f}m away). Pomodoro session reset!"
                self.session_focus_sec = 0.0
                self.continuous_focus_sec = 0.0
                db.record_break()

        # Fetch today's aggregated stats
        daily = db.get_daily_summary()
        pct = min(100.0, (self.session_focus_sec / self.pomodoro_focus_sec) * 100.0)

        return TrackerSnapshot(
            state=current_state,
            continuous_focus_sec=self.continuous_focus_sec,
            session_focus_sec=self.session_focus_sec,
            streak_progress_pct=pct,
            today_focused_sec=daily["focused_seconds"],
            today_distracted_sec=daily["distracted_seconds"],
            today_away_sec=daily["away_seconds"],
            message=msg,
        )
