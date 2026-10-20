# Computer Vision & Facial Recognition: Project Blueprints (Windows & Linux Edition)

This document outlines practical, high-reward computer vision projects that operate safely in user space, with implementation guides for both **Windows** and **Linux (Arch-friendly)**, including low-power optimization for efficient processors (like Intel N-series).

---

# Part I: Cross-Platform Desktop Projects

## Project 1: The "Shoulder Surfer" Privacy Guard 🛡️

### Concept
A background daemon that monitors your webcam feed. If an unknown face appears looking over your shoulder or lingering behind you, it conceals your screen or locks your workstation immediately.

### Key Features
- **User Whitelist:** Learns your face (and trusted contacts) so co-working doesn't trigger false alarms.
- **Threat Detection:** Flags an unrecognized face entering the frame and looking in your screen's direction for > 1.5 seconds.
- **Graduated Responses:**
  - *Level 1 (Subtle):* Minimizes active windows or adds a privacy blur overlay.
  - *Level 2 (Strict):* Locks the session immediately.
- **Intrusion Logging:** Takes a silent snapshot and logs it with a timestamp or sends an alert via Discord webhook.

### Platform Implementation
- **Linux (Arch):**
  - Lock Session: `loginctl lock-session`, `swaylock -f`, or `betterlockscreen -l`
  - Minimize/Hide Windows: `hyprctl dispatch workspace empty` (Hyprland) or `xdotool key super+d` (X11)
  - Camera Node: Direct V4L2 device `/dev/video0`
- **Windows:**
  - Lock Session: `ctypes.windll.user32.LockWorkStation()`
  - Minimize Windows: `pygetwindow` / `pywin32`
- **Core Vision Stack:** `mediapipe` (fast multi-face detection) or `deepface` (ArcFace model).

---

## Project 2: Presence & Attention-Aware Media Controller ⏯️

### Concept
An intelligent media automation tool that tracks whether you are present and actively looking at your monitor. Look away, turn around, or step away, and your media automatically pauses; glance back, and playback resumes.

### Key Features
- **Gaze & Head Pose Tracking:** Estimates head rotation angles (yaw, pitch, roll) and eye gaze direction in real time using 3D facial landmarks.
- **Smart Play / Pause:** Triggers media pause when you look away for more than a configured duration (e.g., 3 seconds).
- **Hysteresis / Debouncing:** Prevents rapid flickering when blinking or glancing down at your keyboard.
- **Auto-Dimming:** Automatically turns off or dims displays when you step away for extended periods.

### Platform Implementation
- **Linux (Arch):**
  - Media Control: `playerctl play-pause` (Controls Spotify, YouTube in Firefox/Chrome, MPV, VLC seamlessly via MPRIS D-Bus)
  - Display Dimming: `brightnessctl set 10%` or `xset dpms force off`
- **Windows:**
  - Media Control: `pyautogui.press('playpause')` or `pynput` media key emulation
  - Display Dimming: `screen_brightness_control`
- **Core Vision Stack:** Google `mediapipe` (Face Mesh with 468 3D landmarks + iris tracking at 60+ FPS on CPU).

---

## Project 3: Smart Desk Assistant & Voice Greeter 🎙️

### Concept
A personalized desk assistant that identifies people approaching your workspace and responds with context-aware voice greetings or visitor alerts.

### Key Features
- **Identity Matching:** Compares incoming faces against a local database of known face embeddings (e.g., *Self*, *Friends*, *Coworkers*).
- **Voice Engine (TTS):**
  - Greets you: *"Welcome back, Loy."*
  - Summarizes brief status updates or unread notifications upon your first morning arrival.
- **Cooldown System:** Implements an identity timeout (e.g., once every 30 minutes) to prevent repeating greetings every time you move in your chair.
- **Unknown Visitor Mode:** Chimes an alert, announces that the desk owner is away, and logs the visitor's image with a timestamp.

### Platform Implementation
- **Linux (Arch):**
  - Voice Synthesis: `piper-tts` (ultra-fast local neural voice) or `spd-say`
  - Desktop Notifications: `notify-send "Desk Alert" "Unknown face detected"`
- **Windows:**
  - Voice Synthesis: `pyttsx3` (SAPI5) or ElevenLabs API
  - Desktop Notifications: `win10toast` or Windows Notification APIs
- **Core Vision Stack:** `insightface` / `deepface` (ArcFace) + `scipy` (cosine similarity) + `sqlite3`.

---

# Part II: Linux-Powered Power-User Projects 🐧

These projects leverage Linux's modular architecture (V4L2, PAM, D-Bus, and Compositor IPC) that are difficult or impossible to implement cleanly on Windows.

## Project 4: Native Face Unlock with Howdy (PAM) 🔓

### Concept
Linux supports modular authentication via **PAM** (Pluggable Authentication Modules). The **Howdy** open-source project hooks directly into PAM, providing native Windows Hello-style biometric authentication.

### Capabilities
- Unlock `sudo` in the terminal using facial recognition.
- Authenticate on system login managers (GDM, SDDM, LightDM).
- Unlock screen lockers (`swaylock`, PAM-compatible lockers).

### Setup on Arch Linux:
```bash
# Install Howdy from AUR
yay -S howdy

# Configure webcam device (usually /dev/video0, or /dev/video2 if using an IR sensor)
sudo howdy config

# Add your face to the database
sudo howdy add

# Test recognition live
sudo howdy test
```

---

## Project 5: Gaze-Driven Tiling Window Focus (Hyprland / Sway / i3) 🪟

### Concept
A hands-free window manager accelerator. Instead of cycling windows using `Super + H/J/K/L` or reaching for the mouse, the camera tracks which monitor split or quadrant your eyes are looking at and automatically transfers window focus.

### How It Works
1. MediaPipe Face Mesh calculates the gaze vector and pupil coordinates relative to your screen geometry.
2. The script determines which window split corresponds to your gaze target.
3. The script dispatches a sub-millisecond IPC call directly to your window manager:
   ```bash
   # Hyprland IPC
   hyprctl dispatch focuswindow <window_id_or_direction>

   # Sway / i3 IPC
   swaymsg focus <direction>
   ```

---

## Project 6: Universal AI Virtual Camera Pipeline (`v4l2loopback`) 🎥

### Concept
Create an AI-augmented camera proxy. The script reads your physical camera (`/dev/video0`), performs real-time computer vision transformations, and pipes the output directly to a virtual video node (`/dev/video1`).

### Applications
- **Real-Time Privacy Anonymizer:** Automatically blurs or pixelates everyone's face except yours before sending the feed to calls.
- **Dynamic Cyberpunk HUD / Face Filters:** Overlays real-time landmark meshes or tracking HUDs.
- **Universal Compatibility:** Every Linux application (Discord, Zoom, Google Meet in browser, OBS) detects `/dev/video1` as a regular, physical hardware webcam.

### Setup on Arch Linux:
```bash
# Install kernel module
sudo pacman -S v4l2loopback-dkms linux-headers

# Create virtual camera device
sudo modprobe v4l2loopback devices=1 video_nr=1 card_label="AI-Webcam" exclusive_caps=1
```

---

## Project 7: Face-Gated Git Commits & GPG Signing 🔐

### Concept
Biometric authorization for developer workflows. Automatically verify your identity before signing Git commits or unlocking sensitive password stores without manually typing a passkey.

---

## Project 8: Dynamic "Persona" & Dotfile Swapper 🎨

### Concept
A multi-user or context-aware environment switcher. When you sit down, the computer recognizes your face and dynamically tailors the desktop environment to your persona.

---

## Project 9: The Multi-Modal "Intent-Gated" Hand & Face Controller 🖐️👀

### Concept
Combines **facial gaze tracking** and **hand gesture recognition** to create an intuitive, zero-false-positive touchless control interface.

> **The Intent Gate Rule:** The system **only** executes hand gesture commands when your face is recognized and your eyes are actively focused on the monitor. If you scratch your nose or sip a drink while looking away, nothing triggers.

### Gesture Command Matrix

| Gesture | Action Triggered (Linux) | Command Executed |
| :--- | :--- | :--- |
| **Open Palm Raised ("Stop")** | Immediate Media Pause | `playerctl pause` |
| **Pinch + Vertical Drag ("Air Dial")**| Smooth Volume Up/Down | `wpctl set-volume @DEFAULT_AUDIO_SINK@ 2%+` (or `-`) |
| **Horizontal Palm Swipe Left/Right** | Skip Track / Prev Track | `playerctl next` / `playerctl previous` |
| **Horizontal Palm Swipe (Hold Super)**| Switch Workspace (Hyprland) | `hyprctl dispatch workspace +1` (or `-1`) |
| **Pointing Finger + Pinch** | Air Mouse Cursor & Click | `ydotool mousemove` / `ydotool click 0xC0` |
| **Quick Closed Fist** | Close Focused Window | `hyprctl dispatch killactive` |

---

## Project 10: "TrueFocus" — Attention-Verified Ergonomics & Time Tracker ⏱️👁️

### Concept
A time-tracking daemon that measures **actual eyes-on-screen focus** instead of basic machine uptime or mouse jiggling.

### Key Features
- **True Screen Time vs. Uptime:** Differentiates between *Active Work* (eyes on display), *Distracted At-Desk* (looking at phone/book), and *Away* (desk empty).
- **Self-Resetting Smart Pomodoro:** Automatically resets your 50-minute work session when you naturally get up for a 5-minute break. Never beeps at you when you just returned from grabbing coffee.
- **20-20-20 Eye Strain Guard:** Prompts you to look 20 feet away for 20 seconds after 20 minutes of continuous focus, and clears the alert once your eyes shift away.
- **Ultra-Low CPU Polling:** Samples the camera at only **0.3 FPS (once every 3 seconds)**, using < 0.5% CPU.

### Architecture
```text
[ Camera Poll (Every 3s) ]
            │
            ▼
┌───────────────────────────────┐
│ Face & Eye Gaze Classification│
└───────────────────────────────┘
  │             │             │
  ▼             ▼             ▼
[ AWAY ]  [ DISTRACTED ]  [ FOCUSED ]
(No face) (Face looking   (Eyes on screen)
            at phone/away)
  │                           │
  ▼                           ▼
Break Timer accumulates    True Screen Time += 3s
If away > 5 mins:          Continuous Streak += 3s
Reset session streak!      If Streak > 50 mins ──▶ 🚨 Break Alert!
```

---

# Part III: Hardware, Battery & DC Power Optimization Guide 🔋

### Hardware Context: Low-TDP Systems (e.g., Intel N-Series / E-Cores)
Low-power chips like the Intel N150 (4 efficiency cores, ~6W–15W TDP, 8 GB RAM) are engineered for exceptional power efficiency. However, running continuous computer vision models without proper throttling will cause thermal throttling and accelerated battery drain.

### How to Run Efficiently on Battery (DC):

| Feature | Naive Implementation (Heavy) | Optimized Implementation (Battery Friendly) |
| :--- | :--- | :--- |
| **Frame Rate** | 30–60 FPS continuous (`100% Core Load`) | **0.2 – 1.0 FPS** event-driven (`< 1% Core Load`) |
| **Webcam Sensor**| Camera sensor powered constantly (~1.2W) | Duty-cycled frames / Sleep between polls |
| **Gesture Engine**| Hand tracking active 100% of time | **Hierarchical:** Hand model only wakes up if Face is present & focused |
| **Inference Backend**| Unoptimized PyTorch CPU | **OpenVINO** or **ONNX Runtime (AVX2-VNNI)** |

### Power-Aware State Machine (AC vs. DC):
```python
import psutil

def get_sampling_interval():
    battery = psutil.sensors_battery()
    if battery and not battery.power_plugged:
        # On Battery (DC): Low power mode
        return 4.0  # Poll once every 4 seconds (negligible battery impact)
    else:
        # Plugged In (AC): High responsiveness
        return 1.0  # Poll every 1 second
```

**Verdict on Battery Life:**
- If run at 30 FPS continuously: Battery life will drop by **30%–50%**.
- If run at optimized 0.3–1.0 FPS intervals with OpenVINO / MediaPipe: Battery drain is virtually indistinguishable from normal browsing (**~5%–8% total impact**, mostly from the physical webcam hardware sensor).

---

# Part IV: Cross-Platform Command Cheat Sheet

| Action | Linux (Arch) Command / Tool | Windows API / Command |
| :--- | :--- | :--- |
| **Media Play/Pause** | `playerctl play-pause` | `pyautogui.press('playpause')` |
| **Audio Volume Control** | `wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+` | `pyautogui.press('volumeup')` |
| **Lock Screen** | `loginctl lock-session` | `ctypes.windll.user32.LockWorkStation()` |
| **Display Dim / Off** | `brightnessctl` / `xset dpms force off` | `screen_brightness_control` |
| **Window WM Focus** | `hyprctl dispatch focuswindow` / `swaymsg` | Complex Win32 Hook (`SetForegroundWindow`) |
| **Close Active Window**| `hyprctl dispatch killactive` | `pyautogui.hotkey('alt', 'f4')` |
| **Virtual Webcam** | `v4l2loopback` (`/dev/video1`) | DirectShow Filter C++ DLL (driver signing required) |
| **Virtual Mouse/Touch**| `ydotool` | `pyautogui` / `pynput` |
| **Desktop Alert** | `notify-send "Title" "Message"` | `win10toast` / PowerShell Toast |
| **Fast Local TTS** | `piper-tts` / `spd-say` | `pyttsx3` (SAPI5) |
| **Camera Node** | `/dev/video0` (V4L2) | DirectShow / Media Foundation index `0` |

---

# Part V: Environment Setup

### Linux (Arch Linux / Pacman / AUR)
```bash
# Core system tools & hardware integration
sudo pacman -S python python-pip playerctl v4l-utils brightnessctl libnotify wireplumber ydotool
# Kernel module for virtual webcam & power-user AUR packages
sudo pacman -S v4l2loopback-dkms linux-headers
yay -S howdy piper-tts-bin

# Python Virtual Environment
python -m venv cv-env
source cv-env/bin/activate
pip install opencv-python mediapipe deepface pynput pyvirtualcam psutil
```

### Windows (PowerShell)
```powershell
python -m venv cv-env
.\cv-env\Scripts\activate
pip install opencv-python mediapipe deepface pynput pyttsx3 pystray screen-brightness-control psutil
```
