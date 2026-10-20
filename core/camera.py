"""
core/camera.py
--------------
Duty-cycle camera capture — open, grab one frame, release immediately.

Why duty-cycle instead of continuous streaming?
  A continuously open camera sensor draws ~1.0–1.5 W even at idle.
  By opening → grabbing → closing on each poll, the sensor is powered
  only for ~50–100 ms per interval, cutting its contribution to near zero.

Usage (duty-cycle / battery-friendly):
    cam = DutyCycleCamera(device=0)
    frame = cam.grab_frame()   # None if camera unavailable

Usage (continuous stream / AC power):
    with DutyCycleCamera(device=0).open_stream() as cap:
        while True:
            ret, frame = cap.read()
"""

import cv2
import numpy as np
from contextlib import contextmanager
from typing import Optional, Generator


class DutyCycleCamera:
    """
    Lightweight camera wrapper optimised for infrequent, duty-cycled polling.
    """

    # Number of warm-up frames to discard before the real capture.
    # Many webcams return a dark/stale frame on the very first read.
    _WARMUP_FRAMES: int = 2

    def __init__(self, device: int = 0, width: int = 640, height: int = 480) -> None:
        self.device = device
        self.width = width
        self.height = height

    # ------------------------------------------------------------------
    # Duty-cycle API (battery-friendly, default)
    # ------------------------------------------------------------------

    def grab_frame(self) -> Optional[np.ndarray]:
        """
        Open the camera, capture one frame, release immediately.

        Returns:
            BGR numpy array, or None if the camera could not be opened.
        """
        cap = cv2.VideoCapture(self.device)
        if not cap.isOpened():
            return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        # Discard warm-up frames
        for _ in range(self._WARMUP_FRAMES):
            cap.grab()

        ret, frame = cap.read()
        cap.release()

        return frame if ret else None

    # ------------------------------------------------------------------
    # Continuous stream API (AC power / high-FPS projects)
    # ------------------------------------------------------------------

    @contextmanager
    def open_stream(self) -> Generator[cv2.VideoCapture, None, None]:
        """
        Context manager that yields an open VideoCapture for continuous reads.

        Example:
            with camera.open_stream() as cap:
                ret, frame = cap.read()
        """
        cap = cv2.VideoCapture(self.device)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera device {self.device}")

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        try:
            yield cap
        finally:
            cap.release()

    def is_available(self) -> bool:
        """Quick check — returns True if the camera device can be opened."""
        cap = cv2.VideoCapture(self.device)
        ok = cap.isOpened()
        cap.release()
        return ok


if __name__ == "__main__":
    cam = DutyCycleCamera()
    frame = cam.grab_frame()
    if frame is not None:
        h, w = frame.shape[:2]
        print(f"Camera OK — captured frame {w}x{h}")
    else:
        print("Camera unavailable")
