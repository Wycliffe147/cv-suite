"""
projects/privacy_guard/__main__.py
-----------------------------------
CLI for Shoulder Surfer Privacy Guard:
- Interactive visual enrollment: python -m projects.privacy_guard --enroll <Name>
- List enrolled faces:          python -m projects.privacy_guard --list
- Clear profile:                python -m projects.privacy_guard --clear <Name>
- Run defense daemon:           python -m projects.privacy_guard
"""

import argparse
import sqlite3
import sys
import time
from core import load_config, DutyCycleCamera
from projects.privacy_guard.face_db import FaceRecognizer, DB_PATH
from projects.privacy_guard.threat import ThreatDetector
from projects.privacy_guard.enroll_ui import run_interactive_enrollment

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
CLEAR = "\033[2K\r"


def list_faces() -> int:
    recognizer = FaceRecognizer()
    enrolled = recognizer.list_enrolled()
    print(f"\n{BOLD}📋 Enrolled Trusted Faces:{RESET}")
    if not enrolled:
        print("  (No faces enrolled yet. Use --enroll <Name> to add your face)\n")
        return 0
    for name, count in enrolled:
        print(f"  • {CYAN}{name}{RESET} ({count} sample embeddings)")
    print()
    return 0


def clear_profile(name: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM enrolled_faces WHERE name = ?", (name,))
        deleted = cursor.rowcount
        conn.commit()
    if deleted > 0:
        print(f"\n{GREEN}✓ Cleared {deleted} sample embeddings for '{name}'.{RESET}\n")
    else:
        print(f"\n{YELLOW}No profile found for '{name}'.{RESET}\n")
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description="Shoulder Surfer Privacy Guard")
    parser.add_argument("--enroll", type=str, metavar="NAME", help="Open visual camera viewfinder to enroll face")
    parser.add_argument("--clear", type=str, metavar="NAME", help="Delete all enrolled embeddings for a person")
    parser.add_argument("--list", action="store_true", help="List enrolled trusted faces")
    parser.add_argument("--threshold", type=float, default=0.42, help="Cosine distance match cutoff (default: 0.42)")
    parser.add_argument("--level1-delay", type=float, default=1.5, help="Seconds before concealing screen (default: 1.5)")
    parser.add_argument("--level2-delay", type=float, default=4.0, help="Seconds before locking workstation (default: 4.0)")
    parser.add_argument("--interval", type=float, default=1.0, help="Poll interval in seconds (default: 1.0)")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.list:
        return list_faces()

    if args.clear:
        return clear_profile(args.clear)

    if args.enroll:
        success = run_interactive_enrollment(args.enroll)
        return 0 if success else 1

    cfg = load_config()
    cam = DutyCycleCamera(device=cfg["camera"]["device"])
    if not cam.is_available():
        print(f"{RED}✗ Camera /dev/video{cfg['camera']['device']} not available.{RESET}")
        return 1

    recognizer = FaceRecognizer(cosine_threshold=args.threshold)
    enrolled = recognizer.list_enrolled()
    if not enrolled:
        print(f"{YELLOW}⚠ Warning: No faces are enrolled in the trusted database!{RESET}")
        print(f"  Run first: {BOLD}python -m projects.privacy_guard --enroll <YourName>{RESET}\n")

    detector = ThreatDetector(
        recognizer=recognizer,
        level1_delay_sec=args.level1_delay,
        level2_delay_sec=args.level2_delay,
    )

    print(f"\n{BOLD}cv-suite · Shoulder Surfer Privacy Guard 🛡️{RESET}")
    print(f"  Trusted Faces:  {[name for name, _ in enrolled] if enrolled else 'None'}")
    print(f"  Match Cutoff:   Cosine <= {args.threshold}")
    print(f"  Level 1 (Hide): {args.level1_delay}s after unknown face appears")
    print(f"  Level 2 (Lock): {args.level2_delay}s if unknown face persists")
    print(f"  Poll interval:  {args.interval}s")
    print(f"\n  Press {BOLD}Ctrl+C{RESET} to stop.\n")

    try:
        while True:
            frame = cam.grab_frame()
            if frame is not None:
                report = detector.evaluate(frame)

                # Format status badge
                if report.level == 2:
                    badge = f"{RED}{BOLD}🚨 LEVEL 2 (LOCKED)   {RESET}"
                elif report.level == 1:
                    badge = f"{YELLOW}{BOLD}🛡️ LEVEL 1 (CONCEALED){RESET}"
                elif report.unknown_count > 0:
                    badge = f"{YELLOW}⚠️ UNKNOWN ({report.threat_duration_sec:.1f}s)    {RESET}"
                elif report.recognized_names:
                    badge = f"{GREEN}🛡️ SECURE (Solo/Trusted){RESET}"
                else:
                    badge = f"{CYAN}🚪 DESK EMPTY          {RESET}"

                names_str = f"Trusted: {', '.join(report.recognized_names) if report.recognized_names else 'None'}"
                faces_str = f"Faces: {report.total_faces} (Unknown: {report.unknown_count})"
                action_str = f"  {BOLD}➜ {report.action_taken}{RESET}" if report.action_taken else ""

                print(f"{CLEAR}{badge} | {faces_str} | {names_str}{action_str}", end="", flush=True)

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n\n{BOLD}Privacy Guard stopped.{RESET}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
