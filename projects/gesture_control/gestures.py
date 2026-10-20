"""
projects/gesture_control/gestures.py
-------------------------------------
Gesture classification & Intent Gate engine:
- Verifies user intent: GESTURES ONLY ACTIVE WHEN FACE IS PRESENT & FOCUSED
- Classifies distinct hand configurations
- Handles cooldowns and smooth delta tracking for Pinch Volume Dial
"""

import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Tuple
from core import FaceEvent
from projects.gesture_control.hand_engine import HandData
from projects.gesture_control import actions


class GestureType(Enum):
    NONE        = auto()
    OPEN_PALM   = auto()  # Pause
    THUMBS_UP   = auto()  # Play
    VICTORY     = auto()  # Next track
    PINCH_DIAL  = auto()  # Volume up / down
    AIR_MOUSE   = auto()  # Pointing index finger moves cursor
    AIR_CLICK   = auto()  # Pinch index+thumb clicks cursor
    FIST        = auto()  # Hold/mute


@dataclass
class GestureEvent:
    gesture: GestureType
    intent_gated: bool       # True if blocked because face wasn't focused
    action_executed: Optional[str] = None
    pinch_delta_y: float = 0.0


class GestureClassifier:
    def __init__(
        self,
        action_cooldown_sec: float = 1.2,
        intent_focus_hold_sec: float = 1.0,   # Eyes must be focused on screen for at least 1s
        intent_release_delay_sec: float = 2.0, # Grace buffer: stay active for 2s after looking away
        volume_step: int = 10,                 # Volume delta percent (+/- 10%)
    ) -> None:
        self.action_cooldown = action_cooldown_sec
        self.intent_focus_hold = intent_focus_hold_sec
        self.intent_release_delay = intent_release_delay_sec
        self.volume_step = volume_step
        self.last_action_time: float = 0.0

        # Intent focus timers
        self.focused_since: Optional[float] = None
        self.last_focused_time: float = 0.0
        self.is_intent_latched: bool = False

        # Pinch drag tracking
        self.last_pinch_y: Optional[float] = None
        self.last_volume_time: float = 0.0

        # Air Mouse tracking
        self.last_index_tip: Optional[Tuple[float, float]] = None
        self.last_click_time: float = 0.0
        self.mouse_smooth_dx: float = 0.0
        self.mouse_smooth_dy: float = 0.0

    def classify(self, hand: Optional[HandData], face_event: FaceEvent) -> GestureEvent:
        now = time.monotonic()
        action_str: Optional[str] = None

        # Update intent focus hold & release grace logic
        if face_event.is_present and face_event.is_focused:
            self.last_focused_time = now
            if self.focused_since is None:
                self.focused_since = now
            elif (now - self.focused_since) >= self.intent_focus_hold:
                # 1.0s continuous focus threshold reached: latch intent open
                self.is_intent_latched = True
        else:
            self.focused_since = None
            # If eyes look away, stay latched for intent_release_delay (2.0s)
            if self.is_intent_latched and (now - self.last_focused_time > self.intent_release_delay):
                self.is_intent_latched = False

        is_intent_active = self.is_intent_latched

        if hand is None:
            self.last_pinch_y = None
            self.last_index_tip = None
            return GestureEvent(gesture=GestureType.NONE, intent_gated=False)

        # ── PRIORITY 1: AIR MOUSE & AIR CLICK ──────────────────────────────
        # When index finger is pointing (aiming at screen)
        if hand.is_pointing:
            tip_x, tip_y, _ = hand.pts[8]  # INDEX_TIP
            self.last_pinch_y = None  # Reset volume dial state while aiming

            # If thumb touches index while pointing -> CLICK!
            if hand.is_pinching:
                detected_gesture = GestureType.AIR_CLICK
                if is_intent_active and (now - self.last_click_time > 0.40):
                    self.last_click_time = now
                    actions.click_mouse("left")
                    action_str = "🖱️ Left Click (Pinch Tap)"
                self.last_index_tip = (tip_x, tip_y)
                return GestureEvent(
                    gesture=detected_gesture,
                    intent_gated=not is_intent_active,
                    action_executed=action_str
                )

            # Otherwise, steer cursor
            detected_gesture = GestureType.AIR_MOUSE
            if self.last_index_tip is not None:
                raw_dx = -(tip_x - self.last_index_tip[0]) * 3.2
                raw_dy = (tip_y - self.last_index_tip[1]) * 3.2

                self.mouse_smooth_dx = self.mouse_smooth_dx * 0.35 + raw_dx * 0.65
                self.mouse_smooth_dy = self.mouse_smooth_dy * 0.35 + raw_dy * 0.65

                send_dx = int(self.mouse_smooth_dx)
                send_dy = int(self.mouse_smooth_dy)

                if is_intent_active and (send_dx != 0 or send_dy != 0):
                    actions.move_mouse(send_dx, send_dy)

            self.last_index_tip = (tip_x, tip_y)
            return GestureEvent(
                gesture=detected_gesture,
                intent_gated=not is_intent_active,
                action_executed=action_str
            )

        self.last_index_tip = None

        # ── PRIORITY 2: PINCH_DIAL (Air Volume Dial +/- 10%) ──────────────
        # Only when NOT in pointing mode (e.g. general pinch posture)
        if hand.is_pinching:
            _, pinch_y = hand.palm_center
            delta_y = 0.0
            act_str = None

            if self.last_pinch_y is not None:
                delta_y = self.last_pinch_y - pinch_y  # Up is positive delta
                if abs(delta_y) > 18 and (now - self.last_volume_time > 0.15):
                    self.last_volume_time = now
                    if is_intent_active:
                        if delta_y > 0:
                            actions.adjust_volume(self.volume_step)
                            act_str = f"🔊 Volume Up (+{self.volume_step}%)"
                        else:
                            actions.adjust_volume(-self.volume_step)
                            act_str = f"🔉 Volume Down (-{self.volume_step}%)"
                    self.last_pinch_y = pinch_y
            else:
                self.last_pinch_y = pinch_y

            return GestureEvent(
                gesture=GestureType.PINCH_DIAL,
                intent_gated=not is_intent_active,
                action_executed=act_str,
                pinch_delta_y=delta_y
            )

        self.last_pinch_y = None

        # ── PRIORITY 3: STATIC MEDIA GESTURES ──────────────────────────────
        i = hand.index_extended
        m = hand.middle_extended
        r = hand.ring_extended
        p = hand.pinky_extended
        t = hand.thumb_extended

        detected_gesture = GestureType.NONE
        action_str = None

        # OPEN PALM: All 5 fingers extended -> PAUSE
        if i and m and r and p and t:
            detected_gesture = GestureType.OPEN_PALM
            if is_intent_active and (now - self.last_action_time > self.action_cooldown):
                self.last_action_time = now
                actions.pause_media()
                action_str = "⏸ Media Paused (Open Palm)"

        # THUMBS UP: Thumb extended, others folded -> PLAY
        elif t and not (i or m or r or p):
            detected_gesture = GestureType.THUMBS_UP
            if is_intent_active and (now - self.last_action_time > self.action_cooldown):
                self.last_action_time = now
                actions.play_media()
                action_str = "▶ Media Playing (Thumbs Up)"

        # VICTORY: Index + Middle up, others folded -> NEXT TRACK
        elif i and m and not (r or p):
            detected_gesture = GestureType.VICTORY
            if is_intent_active and (now - self.last_action_time > self.action_cooldown):
                self.last_action_time = now
                actions.next_track()
                action_str = "⏭ Next Track (Victory)"

        # FIST: All folded -> CLOSED FIST
        elif not (i or m or r or p or t):
            detected_gesture = GestureType.FIST

        return GestureEvent(
            gesture=detected_gesture,
            intent_gated=(not is_intent_active and detected_gesture != GestureType.NONE),
            action_executed=action_str,
        )
