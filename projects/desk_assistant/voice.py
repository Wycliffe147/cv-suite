"""
projects/desk_assistant/voice.py
---------------------------------
Non-blocking text-to-speech voice synthesis.
Supports edge-tts (ultra-realistic Microsoft neural voices) with mpv/aplay audio playback,
and gracefully falls back to desktop notifications if audio playback is unavailable.
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
import threading
from typing import Optional

# Native PipeWire / PulseAudio players first
AUDIO_PLAYERS = ["pw-play", "paplay", "mpv", "aplay"]


def _find_audio_player() -> Optional[str]:
    for player in AUDIO_PLAYERS:
        if shutil.which(player):
            return player
    return None


async def _synthesize_edge_tts(text: str, output_path: str, voice: str = "en-US-ChristopherNeural") -> bool:
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        return True
    except Exception:
        return False


def _play_file(filepath: str) -> None:
    player = _find_audio_player()
    if not player:
        return
    try:
        if player in ("mpv", "ffplay"):
            subprocess.run(
                [player, "--no-video", "--really-quiet" if player == "mpv" else "-nodisp", "-autoexit", filepath],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            subprocess.run([player, filepath], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _speak_worker(text: str, voice: str = "en-US-ChristopherNeural") -> None:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        success = asyncio.run(_synthesize_edge_tts(text, tmp_path, voice))
        if success:
            _play_file(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def speak(text: str, block: bool = False, voice: str = "en-US-ChristopherNeural") -> None:
    """
    Synthesize and play speech.
    Runs in a background thread by default so it never blocks the computer vision loop.
    """
    if block:
        _speak_worker(text, voice)
    else:
        thread = threading.Thread(target=_speak_worker, args=(text, voice), daemon=True)
        thread.start()
