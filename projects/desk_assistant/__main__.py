"""
projects/desk_assistant/__main__.py
------------------------------------
CLI runner for Smart Desk Assistant & Voice Greeter:
- Tracks people approaching your desk
- Greets recognized friends/coworkers with natural voice
- Welcomes unknown visitors and logs visit snapshots
"""

import argparse
import sys
import time
from core import load_config, DutyCycleCamera
from projects.privacy_guard.face_db import FaceRecognizer
from projects.desk_assistant.greeter import DeskGreeter

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
CLEAR = "\033[2K\r"


def parse_args():
    parser = argparse.ArgumentParser(description="Smart Desk Assistant & Voice Greeter")
    parser.add_argument("--test-voice", action="store_true",
                        help="Play a test greeting audio clip immediately and exit")
    parser.add_argument("--cooldown-min", type=float, default=30.0,
                        help="Minutes between repeated greetings for the same person (default: 30)")
    parser.add_argument("--visitor-cooldown-min", type=float, default=5.0,
                        help="Minutes between unknown visitor alerts (default: 5)")
    parser.add_argument("--interval", type=float, default=1.5,
                        help="Camera polling interval in seconds (default: 1.5)")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.test_voice:
        print(f"\n{BOLD}🔊 Testing voice output...{RESET}")
        from projects.desk_assistant import voice
        voice.speak("Hello Sir! The smart desk assistant voice synthesizer is working.", block=True)
        print(f"{GREEN}✓ Test audio finished.{RESET}\n")
        return 0

    cfg = load_config()

    cam = DutyCycleCamera(device=cfg["camera"]["device"])
    if not cam.is_available():
        print(f"{RED}✗ Camera /dev/video{cfg['camera']['device']} not available.{RESET}")
        return 1

    recognizer = FaceRecognizer()
    enrolled = recognizer.list_enrolled()

    print(f"\n{BOLD}cv-suite · Smart Desk Assistant & Voice Greeter 🎙️{RESET}")
    print(f"  Enrolled Profiles:  {[name for name, _ in enrolled] if enrolled else 'None'}")
    print(f"  Greeting Cooldown:  {args.cooldown_min} mins")
    print(f"  Visitor Cooldown:   {args.visitor_cooldown_min} mins")
    print(f"  Poll interval:      {args.interval}s")
    if not enrolled:
        print(f"\n  {YELLOW}Tip: Enroll yourself first using: python -m projects.privacy_guard --enroll <YourName>{RESET}")
    print(f"\n  Press {BOLD}Ctrl+C{RESET} to stop.\n")

    greeter = DeskGreeter(
        recognizer=recognizer,
        cooldown_sec=args.cooldown_min * 60.0,
        visitor_cooldown_sec=args.visitor_cooldown_min * 60.0,
    )

    try:
        while True:
            frame = cam.grab_frame()
            if frame is not None:
                actions = greeter.process_frame(frame)
                if actions:
                    for act in actions:
                        print(f"\n  {GREEN}{BOLD}{act}{RESET}")
                else:
                    print(f"{CLEAR}{CYAN}👁️ Monitoring workspace...{RESET}", end="", flush=True)

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n\n{BOLD}Desk Assistant stopped.{RESET}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
