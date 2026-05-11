import cv2
import numpy as np
from config import CAMERA_SOURCE, MOTION_THRESHOLD, MIN_CONTOUR_AREA


class MotionDetector:
    def __init__(self):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=MOTION_THRESHOLD, detectShadows=False
        )
        self.cap = None

    def open(self):
        self.cap = cv2.VideoCapture(CAMERA_SOURCE)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera: {CAMERA_SOURCE}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    def read_frame(self):
        """Return (frame, motion_detected). frame is None on read failure."""
        ret, frame = self.cap.read()
        if not ret:
            return None, False
        return frame, self._detect_motion(frame)

    def _detect_motion(self, frame):
        fg_mask = self.bg_subtractor.apply(frame)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return any(cv2.contourArea(c) >= MIN_CONTOUR_AREA for c in contours)

    def fps(self):
        return self.cap.get(cv2.CAP_PROP_FPS) or 25.0

    def frame_size(self):
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return w, h

    def close(self):
        if self.cap:
            self.cap.release()
