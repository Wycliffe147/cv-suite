"""
projects/media_controller/media.py
------------------------------------
Thin wrapper around `playerctl` for MPRIS-compatible media control.

Supports any playerctl-compatible player: Spotify, Firefox/YouTube,
Chrome, MPV, VLC, Rhythmbox, etc. — all via the D-Bus MPRIS interface.

Gracefully no-ops when no player is running (never raises).
"""

import subprocess
import shutil
from typing import Optional


def is_available() -> bool:
    """Return True if playerctl CLI binary is found on PATH."""
    return shutil.which("playerctl") is not None


def _playerctl(*args: str) -> Optional[str]:
    """
    Run a playerctl command. Returns stdout on success, None on failure.
    Silent on errors (no player running is not an error worth logging).
    """
    if not shutil.which("playerctl"):
        return None
    try:
        result = subprocess.run(
            ["playerctl", *args],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_status() -> Optional[str]:
    """Return 'Playing', 'Paused', 'Stopped', or None if no player."""
    return _playerctl("status")


def is_playing() -> bool:
    return get_status() == "Playing"


def pause() -> bool:
    """Pause playback. Returns True if command succeeded."""
    return _playerctl("pause") is not None


def play() -> bool:
    """Resume playback. Returns True if command succeeded."""
    return _playerctl("play") is not None


def play_pause() -> bool:
    """Toggle play/pause."""
    return _playerctl("play-pause") is not None


def get_player_name() -> Optional[str]:
    """Return the name of the active player (e.g. 'spotify', 'firefox')."""
    return _playerctl("--player=%any", "status", "--format", "{{playerName}}")
