"""
projects/media_controller/controller.py
-----------------------------------------
Core state machine for the presence & attention-aware media controller.

State transitions (time-based, not frame-count-based so AC/DC interval
changes mid-session are handled correctly):

  WATCHING ──(look away)──► AWAY_COUNTDOWN
                                  │
                         pause_delay elapsed
                                  │
                                  ▼
                              PAUSED ──(look back)──► WATCHING
                                  │
                         dim_delay elapsed
                                  │
                                  ▼
                              DIMMED ──(look back)──► WATCHING

ABSENT (no face at all) is treated identically to LOOKING_AWAY.
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from core import FaceEvent, GazeState, PresenceState
from projects.media_controller import media, display as disp


log = logging.getLogger(__name__)


class ControllerState(Enum):
    WATCHING       = auto()   # Present + focused — everything active
    AWAY_COUNTDOWN = auto()   # Not focused — pause timer ticking
    PAUSED         = auto()   # Media paused — waiting for return
    DIMMED         = auto()   # Media paused + display dimmed


@dataclass
class ControllerStatus:
    """Snapshot returned by MediaController.tick() for the UI / logging."""
    state:          ControllerState
    away_for_secs:  float          # 0 if WATCHING
    media_paused:   bool
    display_dimmed: bool
    gaze:           str
    face_count:     int
    action:         Optional[str] = None   # Human-readable action taken this tick


class MediaController:
    """
    Consumes FaceEvents and drives playerctl + brightnessctl.

    Args:
        mode:         'presence' (pause only when stepping away) or
                      'gaze' (pause when turning head/eyes away).
        pause_delay:  Seconds of inattention/absence before media is paused (default 3s).
        dim_delay:    Additional seconds after pause before display dims (default 60s).
        dim_to:       Target brightness percent when dimming (default 10%).
    """

    def __init__(
        self,
        mode: str = "presence",
        pause_delay: float = 3.0,
        dim_delay:   float = 60.0,
        dim_to:      int   = 10,
    ) -> None:
        self.mode         = mode.lower()
        self.pause_delay  = pause_delay
        self.dim_delay    = dim_delay
        self._display     = disp.DisplayManager(dim_to=dim_to)

        self._state:       ControllerState = ControllerState.WATCHING
        self._away_since:  Optional[float] = None   # monotonic timestamp

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def tick(self, event: FaceEvent) -> ControllerStatus:
        """
        Process one FaceEvent and update state. Returns a ControllerStatus.
        This method is idempotent — safe to call at any frequency.
        """
        now    = time.monotonic()
        action = None

        # Check condition based on mode:
        # In 'presence' mode: Active as long as head/face is present at desk.
        # In 'gaze' mode: Active only when face is present AND looking at screen.
        if self.mode == "presence":
            is_active = event.is_present
        else:
            is_active = event.is_focused

        if is_active:
            action = self._handle_focused(now)
        else:
            action = self._handle_unfocused(now)

        away_for = (now - self._away_since) if self._away_since else 0.0

        return ControllerStatus(
            state=self._state,
            away_for_secs=away_for,
            media_paused=self._state in (ControllerState.PAUSED, ControllerState.DIMMED),
            display_dimmed=self._display.is_dimmed,
            gaze=event.gaze.name,
            face_count=event.face_count,
            action=action,
        )

    # ------------------------------------------------------------------
    # Private state handlers
    # ------------------------------------------------------------------

    def _handle_focused(self, now: float) -> Optional[str]:
        """User is present and looking at the screen — restore everything."""
        action = None

        if self._state == ControllerState.DIMMED:
            self._display.restore()
            media.play()
            action = "▶  Restored brightness + resumed playback"
            log.info(action)

        elif self._state == ControllerState.PAUSED:
            media.play()
            action = "▶  Resumed playback"
            log.info(action)

        elif self._state == ControllerState.AWAY_COUNTDOWN:
            away_for = now - self._away_since if self._away_since else 0
            action = f"↩  Returned after {away_for:.1f}s (before pause threshold)"
            log.debug(action)

        self._away_since = None
        self._state      = ControllerState.WATCHING
        return action

    def _handle_unfocused(self, now: float) -> Optional[str]:
        """User is absent or looking away — run countdown → pause → dim."""
        action = None

        # Start the away timer on first unfocused frame
        if self._away_since is None:
            self._away_since = now
            self._state = ControllerState.AWAY_COUNTDOWN
            log.debug("Away timer started")
            return action

        away_for = now - self._away_since

        if self._state == ControllerState.DIMMED:
            return None   # Already at max response — nothing more to do

        if self._state == ControllerState.PAUSED:
            # Check if it's time to dim
            if away_for >= self.pause_delay + self.dim_delay:
                self._display.dim()
                self._state = ControllerState.DIMMED
                action = f"🌑 Dimmed display after {away_for:.0f}s away"
                log.info(action)
            return action

        # AWAY_COUNTDOWN — check if pause threshold crossed
        if away_for >= self.pause_delay:
            media.pause()
            self._state = ControllerState.PAUSED
            action = f"⏸  Paused after {away_for:.1f}s away"
            log.info(action)

        return action

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Restore display brightness on exit."""
        if self._display.is_dimmed:
            self._display.restore()
