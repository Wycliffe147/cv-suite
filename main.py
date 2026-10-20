"""
main.py
--------
Core engine smoke-test — verifies the entire Phase 1 stack in one run.

Run:
    source cv-env/bin/activate
    python main.py

What it checks:
  1. Config loads correctly from core/config.toml
  2. Power state is detected (AC vs battery)
  3. Camera is available and can grab a frame
  4. FaceEngine processes the frame and emits a valid FaceEvent
"""

import sys
import time

from core import (
    load_config,
    get_power_state,
    get_sampling_interval,
    DutyCycleCamera,
    FaceEngine,
    GazeState,
    PresenceState,
)

RESET  = "\033[0m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"

def ok(msg):  print(f"  {GREEN}✓{RESET} {msg}")
def warn(msg):print(f"  {YELLOW}⚠{RESET} {msg}")
def fail(msg):print(f"  {RED}✗{RESET} {msg}")


def main() -> int:
    print(f"\n{BOLD}cv-suite — Phase 1 Core Engine Smoke-Test{RESET}\n")

    # 1. Config
    print("① Loading config …")
    try:
        cfg = load_config()
        ok(f"config.toml loaded — device={cfg['camera']['device']}, "
           f"ac_interval={cfg['sampling']['ac_interval']}s, "
           f"dc_interval={cfg['sampling']['dc_interval']}s")
    except Exception as e:
        fail(f"Config load failed: {e}")
        return 1

    # 2. Power state
    print("\n② Detecting power state …")
    power  = get_power_state()
    source = "Battery" if power.on_battery else "AC / Plugged in"
    pct    = f" ({power.battery_percent}%)" if power.battery_percent is not None else ""
    ok(f"Power source: {source}{pct}")

    interval = get_sampling_interval(
        ac_interval=cfg["sampling"]["ac_interval"],
        dc_interval=cfg["sampling"]["dc_interval"],
    )
    ok(f"Sampling interval: {interval}s")

    # 3. Camera
    print("\n③ Checking camera …")
    cam = DutyCycleCamera(
        device=cfg["camera"]["device"],
        width=cfg["camera"]["width"],
        height=cfg["camera"]["height"],
    )
    if not cam.is_available():
        fail(f"Camera device {cfg['camera']['device']} not found. "
             "Check 'device' in core/config.toml.")
        return 1
    ok(f"Camera /dev/video{cfg['camera']['device']} available")

    # 4. FaceEngine — grab & process 3 frames
    print(f"\n④ Running FaceEngine (3 frames, {interval}s apart) …\n")
    face_cfg  = cfg["face"]
    pose_cfg  = cfg["head_pose"]
    model_cfg = cfg["models"]

    with FaceEngine(
        model_path=model_cfg["face_landmarker"],
        max_faces=face_cfg["max_faces"],
        min_detection_confidence=face_cfg["min_detection_confidence"],
        min_presence_confidence=face_cfg["min_presence_confidence"],
        min_tracking_confidence=face_cfg["min_tracking_confidence"],
        yaw_threshold=pose_cfg["yaw_threshold"],
        pitch_up_threshold=pose_cfg.get("pitch_up_threshold", 25.0),
        pitch_down_threshold=pose_cfg.get("pitch_down_threshold", 40.0),
    ) as engine:

        for i in range(3):
            frame = cam.grab_frame()
            if frame is None:
                warn(f"Frame {i+1}: failed to grab — skipping")
                continue

            event = engine.process(frame)

            pose_str = (
                f"yaw={event.head_pose.yaw:+.1f}°  "
                f"pitch={event.head_pose.pitch:+.1f}°  "
                f"roll={event.head_pose.roll:+.1f}°"
            ) if event.head_pose else "pose=N/A"

            gaze_color = GREEN if event.gaze == GazeState.LOOKING_AT_SCREEN else (
                         YELLOW if event.gaze == GazeState.LOOKING_AWAY else RESET)

            print(
                f"    Frame {i+1}:  "
                f"presence={event.presence.name:<8}  "
                f"gaze={gaze_color}{event.gaze.name:<22}{RESET}  "
                f"faces={event.face_count}  "
                f"[{pose_str}]"
            )
            if i < 2:
                time.sleep(interval)

    print(f"\n{GREEN}{BOLD}Phase 1 smoke-test complete.{RESET}\n"
          "Next step: build projects/media_controller/ (Phase 2)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
