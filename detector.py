import cv2
import numpy as np
from config import CAMERA_SOURCE, MOTION_THRESHOLD, MIN_CONTOUR_AREA

_USE_PICAMERA = CAMERA_SOURCE == "picamera"


class MotionDetector:
    def __init__(self):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=MOTION_THRESHOLD, detectShadows=False
        )
        self._cam = None
        self._fps = 25.0
        self._frame_size = (1280, 720)

    def open(self):
        if _USE_PICAMERA:
            from picamera2 import Picamera2
            self._cam = Picamera2()
            config = self._cam.create_video_configuration(
                main={"size": (1280, 720), "format": "BGR888"}
            )
            self._cam.configure(config)
            self._cam.start()
            self._fps = 25.0
            self._frame_size = (1280, 720)
        else:
            self._cam = cv2.VideoCapture(CAMERA_SOURCE)
            if not self._cam.isOpened():
                raise RuntimeError(f"Cannot open camera: {CAMERA_SOURCE}")
            self._cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self._cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self._fps = self._cam.get(cv2.CAP_PROP_FPS) or 25.0
            self._frame_size = (
                int(self._cam.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self._cam.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )

    def read_frame(self):
        """Return (frame, motion_detected). frame is None on read failure."""
        if _USE_PICAMERA:
            frame = self._cam.capture_array("main")
            # IMX708 is mounted upside-down on most Pi Camera Module 3 cases
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        else:
            ret, frame = self._cam.read()
            if not ret:
                return None, False
        return frame, self._detect_motion(frame)

    def _detect_motion(self, frame):
        fg_mask = self.bg_subtractor.apply(frame)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return any(cv2.contourArea(c) >= MIN_CONTOUR_AREA for c in contours)

    def fps(self):
        return self._fps

    def frame_size(self):
        return self._frame_size

    def close(self):
        if self._cam:
            if _USE_PICAMERA:
                self._cam.stop()
            else:
                self._cam.release()
