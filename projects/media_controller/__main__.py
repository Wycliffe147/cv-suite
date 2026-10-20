"""
projects/media_controller/__main__.py
---------------------------------------
Entry point — run as:

    source cv-env/bin/activate
    python -m projects.media_controller

    # With custom thresholds:
    python -m projects.media_controller --pause-delay 5 --dim-delay 120

Press Ctrl+C to stop. Display brightness is restored on exit.
"""

import argparse
import logging
import signal
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
from projects.media_controller.controller import MediaController, ControllerState

# ── Colour codes ───────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
DIM    = "\033[2m"
RED    = "\033[91m"
CLEAR  = "\033[2K\r"   # clear current line

# ── State → colour + icon ─────────────────────────────────────────────────
STATE_STYLE = {
    ControllerState.WATCHING:       (GREEN,  "👁  WATCHING      "),
    ControllerState.AWAY_COUNTDOWN: (YELLOW, "⏳ AWAY          "),
    ControllerState.PAUSED:         (CYAN,   "⏸  PAUSED        "),
    ControllerState.DIMMED:         (DIM,    "🌑 DIMMED        "),
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Presence and attention-aware media controller")
    p.add_argument("--mode", type=str, choices=["presence", "gaze"], default=None,
                   help="Control mode: 'presence' (pause on desk departure) or 'gaze' (pause on looking away)")
    p.add_argument("--pause-delay", type=float, default=None,
                   help="Seconds of absence/inattention before pausing")
    p.add_argument("--dim-delay", type=float, default=None,
                   help="Extra seconds after pause before dimming")
    p.add_argument("--dim-to", type=int, default=None,
                   help="Target brightness %% when dimming")
    p.add_argument("--verbose", action="store_true",
                   help="Enable debug logging")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = load_config()
    media_cfg = cfg.get("media_controller", {})

    mode = args.mode or media_cfg.get("mode", "presence")
    pause_delay = args.pause_delay if args.pause_delay is not None else media_cfg.get("pause_delay", 3.0)
    dim_delay = args.dim_delay if args.dim_delay is not None else media_cfg.get("dim_delay", 60.0)
    dim_to = args.dim_to if args.dim_to is not None else media_cfg.get("dim_to", 10)

    cam = DutyCycleCamera(
        device=cfg["camera"]["device"],
        width=cfg["camera"]["width"],
        height=cfg["camera"]["height"],
    )

    if not cam.is_available():
        print(f"{RED}✗ Camera not available. Check config.toml → [camera] device.{RESET}")
        return 1

    controller = MediaController(
        mode=mode,
        pause_delay=pause_delay,
        dim_delay=dim_delay,
        dim_to=dim_to,
    )

    from projects.media_controller import media
    if not media.is_available():
        print(f"{YELLOW}⚠  'playerctl' is not installed! Media control won't work.{RESET}")
        print(f"   Install it via: {BOLD}sudo pacman -S playerctl{RESET}\n")

    # Restore brightness on SIGTERM / SIGINT
    def _shutdown(sig, frame):
        print(f"\n{BOLD}Shutting down …{RESET}")
        controller.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    face_cfg = cfg["face"]
    pose_cfg = cfg["head_pose"]

    print(f"\n{BOLD}cv-suite · Media Controller{RESET}")
    print(f"  Mode:         {CYAN}{BOLD}{mode.upper()}{RESET} ({'Pauses when you leave desk' if mode == 'presence' else 'Pauses when you look away'})")
    print(f"  Pause after:  {pause_delay}s absence")
    print(f"  Dim after:    {pause_delay + dim_delay:.0f}s absence")
    print(f"  Dim to:       {dim_to}%")
    print(f"\n  Press {BOLD}Ctrl+C{RESET} to stop.\n")

    with FaceEngine(
        model_path=cfg["models"]["face_landmarker"],
        max_faces=face_cfg["max_faces"],
        min_detection_confidence=face_cfg["min_detection_confidence"],
        min_presence_confidence=face_cfg["min_presence_confidence"],
        min_tracking_confidence=face_cfg["min_tracking_confidence"],
        yaw_threshold=pose_cfg["yaw_threshold"],
        pitch_up_threshold=pose_cfg.get("pitch_up_threshold", 25.0),
        pitch_down_threshold=pose_cfg.get("pitch_down_threshold", 40.0),
    ) as engine:

        while True:
            # Adapt sampling interval to power source each loop iteration
            interval = get_sampling_interval(
                ac_interval=cfg["sampling"]["ac_interval"],
                dc_interval=cfg["sampling"]["dc_interval"],
            )

            frame = cam.grab_frame()
            if frame is None:
                print(f"{CLEAR}{YELLOW}⚠  Camera read failed — retrying …{RESET}", end="", flush=True)
                time.sleep(interval)
                continue

            event  = engine.process(frame)
            status = controller.tick(event)

            # ── Live status line ──────────────────────────────────────────
            colour, label = STATE_STYLE.get(
                status.state, (RESET, str(status.state))
            )
            away_str = (
                f"  away {status.away_for_secs:.0f}s"
                if status.away_for_secs > 0 else ""
            )
            faces_str = f"  faces={status.face_count}"
            action_str = (
                f"  {BOLD}→ {status.action}{RESET}" if status.action else ""
            )

            print(
                f"{CLEAR}{colour}{BOLD}{label}{RESET}"
                f"{DIM}{faces_str}{away_str}{RESET}"
                f"{action_str}",
                end="",
                flush=True,
            )

            time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
