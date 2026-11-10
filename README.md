# 👁️ cv-suite — Computer Vision & Facial Recognition Suite

A unified, modular computer vision toolkit for Linux (Hyprland / Arch-optimized) and desktop workstations.

---

## 🚀 Projects Built in the Suite

| Project | Folder | Description | Command |
|---|---|---|---|
| **Unified Background Daemon** | [`daemon.py`](file:///home/wy/Projects/cv-suite/daemon.py) | Coordinates all 4 services on 1 single camera poll & vision pass | `systemctl --user start cv-suite` |
| **Phase 1: Core Vision Engine** | [`core/`](file:///home/wy/Projects/cv-suite/core/) | Shared MediaPipe Face Landmarker, solvePnP 3D pose, AC/DC duty-cycle | `python main.py` |
| **Phase 2: Media Controller** | [`projects/media_controller/`](file:///home/wy/Projects/cv-suite/projects/media_controller/) | Presence / attention-aware auto pause & resume via `playerctl` & `brightnessctl` | `python -m projects.media_controller` |
| **Phase 3: TrueFocus Ergonomics** | [`projects/truefocus/`](file:///home/wy/Projects/cv-suite/projects/truefocus/) | Attention-verified time tracker, smart Pomodoro, 20-20-20 eye strain guard | `python -m projects.truefocus` |
| **Phase 4: Shoulder Surfer Guard** | [`projects/privacy_guard/`](file:///home/wy/Projects/cv-suite/projects/privacy_guard/) | SFace ArcFace matching, interactive visual enrollment, Omarchy screen lock | `python -m projects.privacy_guard` |
| **Phase 5: Smart Desk Assistant** | [`projects/desk_assistant/`](file:///home/wy/Projects/cv-suite/projects/desk_assistant/) | Neural voice greeter, 30m cooldown, unknown visitor chime & snapshot logger | `python -m projects.desk_assistant` |
| **Phase 6: Multi-Modal Gestures** | [`projects/gesture_control/`](file:///home/wy/Projects/cv-suite/projects/gesture_control/) | Intent-gated hand control (Open palm, thumbs up, victory, pinch volume dial) | `python -m projects.gesture_control --hud` |

---

## ⚙️ Background Daemon (Auto-Start on Login)

The suite now runs as an autonomous, single-process background daemon (`cv-suite.service`) via systemd user services. All features share one camera capture and one vision pass, preventing device lockouts and keeping CPU usage minimal.

```bash
# Check live status & recent background logs
systemctl --user status cv-suite

# View live log stream
journalctl --user -u cv-suite -f

# Stop or restart daemon
systemctl --user stop cv-suite
systemctl --user restart cv-suite
```

### Toggle features in [`core/config.toml`](file:///home/wy/Projects/cv-suite/core/config.toml):
```toml
[daemon]
enable_media_controller = true
enable_privacy_guard = true
enable_desk_assistant = true
enable_truefocus = true
```

---

---

## 🛠️ Quick Commands

```bash
cd /home/wy/Projects/cv-suite
source cv-env/bin/activate

# 1. Enroll face with interactive camera viewfinder (with lighting meter)
python -m projects.privacy_guard --enroll Sir

# 2. Run Privacy Guard (Locks screen if someone lingers behind you)
python -m projects.privacy_guard

# 3. Run Desk Assistant (Speaks neural voice greetings)
python -m projects.desk_assistant

# 4. Run Intent-Gated Hand Gesture Controller (with visual HUD)
python -m projects.gesture_control --hud

# 5. Run Media Controller (Pauses media when you step away)
python -m projects.media_controller

# 6. Check Daily Focus Report
python -m projects.truefocus --report
```

---

## 🖐️ Gesture Command Matrix (Phase 6)

| Gesture | Action | System Integration |
|---|---|---|
| **Raised Open Palm** 🖐️ | Pause Media | `playerctl pause` |
| **Thumbs Up** 👍 | Resume Playback | `playerctl play` |
| **Victory / Peace (V)** ✌️ | Next Track | `playerctl next` |
| **Pinch + Vertical Drag** 👌 | Smooth Volume Dial (Up / Down) | `wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%±` |

> **The Intent Gate Rule:** Hand gestures only execute when your face is present and looking at your screen. Gestures made while looking away or scratching your face are completely ignored!
