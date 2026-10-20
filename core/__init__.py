"""
core/__init__.py
-----------------
Public API surface for the core engine.

Projects import from here:
    from core import FaceEngine, FaceEvent, GazeState, PresenceState
    from core import DutyCycleCamera
    from core import get_sampling_interval, get_power_state
    from core import load_config
"""

from core.face_engine import (
    FaceEngine,
    FaceEvent,
    GazeState,
    PresenceState,
    HeadPose,
)
from core.camera import DutyCycleCamera
from core.state  import get_sampling_interval, get_power_state, PowerState
from core.config_loader import load_config

__all__ = [
    # Vision
    "FaceEngine",
    "FaceEvent",
    "GazeState",
    "PresenceState",
    "HeadPose",
    # Camera
    "DutyCycleCamera",
    # Power
    "get_sampling_interval",
    "get_power_state",
    "PowerState",
    # Config
    "load_config",
]
