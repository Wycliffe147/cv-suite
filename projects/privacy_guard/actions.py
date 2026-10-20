"""
projects/privacy_guard/actions.py
----------------------------------
System privacy defense actions for Omarchy / Hyprland / Linux desktop:
- Level 1: Conceal screen (screensaver / black overlay)
- Level 2: Lock workstation (omarchy-system-lock / omarchy-shell lock lock)
- Snapshot logger: Silently capture intruder image
"""

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
import cv2
import numpy as np

SNAPSHOT_DIR = Path(__file__).parents[2] / "data" / "snapshots"


def lock_screen() -> bool:
    """Lock the Linux desktop session."""
    # 1. Omarchy / Hyprland official lock commands
    if shutil.which("omarchy-system-lock"):
        try:
            subprocess.Popen(["omarchy-system-lock"])
            return True
        except Exception:
            pass

    if shutil.which("omarchy-shell"):
        try:
            subprocess.Popen(["omarchy-shell", "lock", "lock"])
            return True
        except Exception:
            pass

    # 2. Hyprlock / Swaylock
    for locker in ["hyprlock", "swaylock"]:
        if shutil.which(locker):
            try:
                subprocess.Popen([locker])
                return True
            except Exception:
                pass

    # 3. Systemd loginctl fallback
    if shutil.which("loginctl"):
        try:
            subprocess.run(["loginctl", "lock-session"], capture_output=True, timeout=2)
            return True
        except Exception:
            pass

    return False


def conceal_screen() -> bool:
    """Subtle Level 1 action: activate screensaver or turn display off momentarily."""
    # 1. Omarchy screensaver
    if shutil.which("omarchy-screensaver"):
        try:
            subprocess.Popen(["omarchy-screensaver"])
            return True
        except Exception:
            pass

    # 2. Hyprland DPMS off (blanks monitor instantly)
    if shutil.which("hyprctl"):
        try:
            res = subprocess.run(["hyprctl", "dispatch", "dpms", "off"], capture_output=True, timeout=2)
            if res.returncode == 0:
                return True
        except Exception:
            pass

    # 3. X11 via xdotool (minimize all / show desktop)
    if shutil.which("xdotool"):
        try:
            res = subprocess.run(["xdotool", "key", "super+d"], capture_output=True, timeout=2)
            if res.returncode == 0:
                return True
        except Exception:
            pass

    return False


def save_snapshot(frame: np.ndarray, tag: str = "intruder") -> Optional[Path]:
    """Silently save an intruder snapshot with timestamp."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = SNAPSHOT_DIR / f"{tag}_{timestamp}.jpg"
    try:
        cv2.imwrite(str(filepath), frame)
        return filepath
    except Exception:
        return None
