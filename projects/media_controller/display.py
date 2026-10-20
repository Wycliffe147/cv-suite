"""
projects/media_controller/display.py
--------------------------------------
Brightness control via `brightnessctl` (Linux/Wayland/X11).

Saves current brightness before dimming so it can be restored exactly.
Gracefully no-ops when brightnessctl is not installed.
"""

import subprocess
import shutil
from typing import Optional


def _brightnessctl(*args: str) -> Optional[str]:
    if not shutil.which("brightnessctl"):
        return None
    try:
        result = subprocess.run(
            ["brightnessctl", *args],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_brightness_percent() -> Optional[int]:
    """Return current brightness as 0–100 integer, or None if unavailable."""
    raw = _brightnessctl("get")
    max_raw = _brightnessctl("max")
    if raw is None or max_raw is None:
        return None
    try:
        return round(int(raw) / int(max_raw) * 100)
    except (ValueError, ZeroDivisionError):
        return None


def set_brightness(percent: int) -> bool:
    """Set brightness to `percent` (0–100). Returns True on success."""
    pct = max(1, min(100, percent))  # clamp — never go fully dark
    return _brightnessctl("set", f"{pct}%") is not None


class DisplayManager:
    """
    Manages brightness with save/restore so dimming is always reversible.

    Usage:
        dm = DisplayManager(dim_to=10)
        dm.dim()       # dims to 10%, saves original level
        dm.restore()   # back to original level
    """

    def __init__(self, dim_to: int = 10) -> None:
        self.dim_to = dim_to
        self._saved_brightness: Optional[int] = None
        self.available = shutil.which("brightnessctl") is not None

    def dim(self) -> None:
        if not self.available:
            return
        current = get_brightness_percent()
        if current is not None and current > self.dim_to:
            self._saved_brightness = current
            set_brightness(self.dim_to)

    def restore(self) -> None:
        if not self.available:
            return
        if self._saved_brightness is not None:
            set_brightness(self._saved_brightness)
            self._saved_brightness = None

    @property
    def is_dimmed(self) -> bool:
        return self._saved_brightness is not None
