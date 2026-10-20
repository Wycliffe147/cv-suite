"""
projects/truefocus/__main__.py
--------------------------------
CLI for TrueFocus Attention-Verified Ergonomics & Time Tracker.

Usage:
  # Run continuous daemon
  python -m projects.truefocus

  # View daily summary report
  python -m projects.truefocus --report

Options:
  --pomodoro-min <mins>   Target focus duration per session (default: 50)
  --away-reset-min <mins> Auto-reset session if away for this long (default: 5)
  --interval <sec>        Polling interval in seconds (default: 3.0)
"""

import argparse
import sys
import time
from datetime import date
from core import load_config, DutyCycleCamera, FaceEngine
from projects.truefocus.tracker import FocusTracker
from projects.truefocus import db

# Color formatting
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
CLEAR = "\033[2K\r"


def format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m:02d}m {s:02d}s"


def print_report():
    db.init_db()
    summary = db.get_daily_summary()
    total_tracked = summary["focused_seconds"] + summary["distracted_seconds"] + summary["away_seconds"]
    
    print(f"\n{BOLD}📊 TrueFocus Daily Report — {summary['date']}{RESET}")
    print("=" * 45)
    print(f"🎯 Total Active Focus:      {GREEN}{format_duration(summary['focused_seconds'])}{RESET}")
    print(f"📱 Distracted at Desk:      {YELLOW}{format_duration(summary['distracted_seconds'])}{RESET}")
    print(f"🚪 Away from Desk:          {CYAN}{format_duration(summary['away_seconds'])}{RESET}")
    print(f"☕ Breaks Logged:           {BOLD}{summary['breaks_taken']}{RESET}")
    
    if total_tracked > 0:
        ratio = (summary["focused_seconds"] / total_tracked) * 100
        print(f"📈 Focus Efficiency Score:  {BOLD}{ratio:.1f}%{RESET}")
    print("=" * 45 + "\n")


def parse_args():
    parser = argparse.ArgumentParser(description="TrueFocus Ergonomics & Time Tracker")
    parser.add_argument("--report", action="store_true", help="Print daily focus report and exit")
    parser.add_argument("--pomodoro-min", type=float, default=50.0, help="Session target minutes (default: 50)")
    parser.add_argument("--away-reset-min", type=float, default=5.0, help="Away minutes to reset session (default: 5)")
    parser.add_argument("--interval", type=float, default=3.0, help="Duty-cycle poll interval (default: 3.0s)")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.report:
        print_report()
        return 0

    cfg = load_config()
    cam = DutyCycleCamera(
        device=cfg["camera"]["device"],
        width=cfg["camera"]["width"],
        height=cfg["camera"]["height"]
    )

    if not cam.is_available():
        print(f"{RED}✗ Camera /dev/video{cfg['camera']['device']} not available.{RESET}")
        return 1

    tracker = FocusTracker(
        pomodoro_focus_min=args.pomodoro_min,
        away_reset_min=args.away_reset_min
    )

    face_cfg = cfg["face"]
    pose_cfg = cfg["head_pose"]

    print(f"\n{BOLD}cv-suite · TrueFocus Attention & Ergonomics Tracker{RESET}")
    print(f"  Target Session: {args.pomodoro_min} mins")
    print(f"  Away Reset:     {args.away_reset_min} mins")
    print(f"  Polling Rate:   Every {args.interval}s")
    print(f"\n  Press {BOLD}Ctrl+C{RESET} to finish session.\n")

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
        try:
            while True:
                frame = cam.grab_frame()
                if frame is not None:
                    event = engine.process(frame)
                    snap = tracker.tick(event)

                    # State color badge
                    if snap.state == "FOCUSED":
                        badge = f"{GREEN}{BOLD}🎯 FOCUSED    {RESET}"
                    elif snap.state == "DISTRACTED":
                        badge = f"{YELLOW}{BOLD}📱 DISTRACTED {RESET}"
                    else:
                        badge = f"{CYAN}{BOLD}🚪 AWAY       {RESET}"

                    progress_bar_len = 10
                    filled = int((snap.streak_progress_pct / 100.0) * progress_bar_len)
                    bar = f"[{'#' * filled}{'-' * (progress_bar_len - filled)}]"

                    status_line = (
                        f"{CLEAR}{badge} "
                        f"Session: {format_duration(snap.session_focus_sec)} {bar} {snap.streak_progress_pct:.0f}% | "
                        f"Today Focus: {format_duration(snap.today_focused_sec)}"
                    )
                    if snap.message:
                        status_line += f"  {BOLD}🔔 {snap.message}{RESET}"

                    print(status_line, end="", flush=True)

                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n")
            print_report()
            return 0


if __name__ == "__main__":
    sys.exit(main())
