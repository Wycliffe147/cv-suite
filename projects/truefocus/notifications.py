"""
projects/truefocus/notifications.py
------------------------------------
Desktop notifications using notify-send (libnotify).
"""

import shutil
import subprocess
from typing import Optional


def send_notification(title: str, message: str, urgency: str = "normal", icon: Optional[str] = None) -> bool:
    """Send a desktop notification via notify-send. Urgency can be low, normal, or critical."""
    if not shutil.which("notify-send"):
        return False
    cmd = ["notify-send", "-u", urgency]
    if icon:
        cmd.extend(["-i", icon])
    cmd.extend([title, message])
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
