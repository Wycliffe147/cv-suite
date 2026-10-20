"""
projects/gesture_control/actions.py
------------------------------------
System action dispatchers for hand gestures:
- Volume control via WirePlumber (wpctl)
- Media control via playerctl (play, pause, next, prev)
- Window / Screen actions (Hyprland / Omarchy)
"""

import shutil
import subprocess
from typing import Optional


def move_mouse(dx: int, dy: int) -> bool:
    """Move cursor by relative (dx, dy) pixels using ydotool."""
    if not shutil.which("ydotool") or (dx == 0 and dy == 0):
        return False
    try:
        # Note: Do NOT use -w (which scrolls wheel). Use -- dx dy for relative pointer movement.
        subprocess.run(["ydotool", "mousemove", "--", str(dx), str(dy)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.1)
        return True
    except Exception:
        return False


def click_mouse(button: str = "left") -> bool:
    """Perform a mouse click (left or right)."""
    if not shutil.which("ydotool"):
        return False
    # 0xC0 is left click in ydotool hex code (BTN_LEFT: 0x110)
    # ydotool click 0xC0 (left down + up)
    hex_code = "0xC0" if button == "left" else "0xC1"
    try:
        subprocess.run(["ydotool", "click", hex_code],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.2)
        return True
    except Exception:
        return False


def adjust_volume(delta_percent: int) -> bool:
    """Increase or decrease system volume by delta_percent (e.g. +5 or -5)."""
    if not shutil.which("wpctl"):
        return False
    sign = "+" if delta_percent >= 0 else "-"
    arg = f"{abs(delta_percent)}%{sign}"
    try:
        subprocess.run(
            ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", arg],
            capture_output=True, timeout=1
        )
        return True
    except Exception:
        return False


def play_media() -> bool:
    if shutil.which("playerctl"):
        try:
            subprocess.run(["playerctl", "play"], capture_output=True, timeout=1)
            return True
        except Exception:
            pass
    return False


def pause_media() -> bool:
    if shutil.which("playerctl"):
        try:
            subprocess.run(["playerctl", "pause"], capture_output=True, timeout=1)
            return True
        except Exception:
            pass
    return False


def next_track() -> bool:
    if shutil.which("playerctl"):
        try:
            subprocess.run(["playerctl", "next"], capture_output=True, timeout=1)
            return True
        except Exception:
            pass
    return False


def prev_track() -> bool:
    if shutil.which("playerctl"):
        try:
            subprocess.run(["playerctl", "previous"], capture_output=True, timeout=1)
            return True
        except Exception:
            pass
    return False
