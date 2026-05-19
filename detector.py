import cv2
import numpy as np
from config import (CAMERA_SOURCE, MOTION_THRESHOLD, MIN_CONTOUR_AREA,
                    PRE_BUFFER_SECONDS, MOTION_ROI)

_USE_PICAMERA = CAMERA_SOURCE == "picamera"

# Fixed camera colour/exposure controls (libcamera).
# AwbMode 5 = Daylight — corrects the IMX708's cool/blue bias.
CAMERA_CONTROLS = {
    "AeEnable": True,
    "AwbEnable": True,
    "AwbMode": 5,
}


class MotionDetector:
    def __init__(self):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=MOTION_THRESHOLD, detectShadows=False
        )
        # Motion detection runs on a half-size frame to cut CPU; contour
        # areas there are quartered, so scale the threshold to match.
        self._motion_scale = 0.5
        self._min_area = MIN_CONTOUR_AREA * self._motion_scale ** 2
        self._kernel = np.ones((3, 3), np.uint8)
        self._cam = None
        self._encoder = None
        self._circular = None
        self._fps = 25.0
        self._frame_size = (1280, 720)

    def open(self):
        if _USE_PICAMERA:
            from picamera2 import Picamera2
            from libcamera import Transform
            self._cam = Picamera2()
            config = self._cam.create_video_configuration(
                main={"size": (1280, 720), "format": "BGR888"},
                controls={"FrameRate": 30},
                # Camera is mounted upside down — flip in the ISP (free)
                # instead of rotating every frame on the CPU.
                transform=Transform(hflip=1, vflip=1),
            )
            self._cam.configure(config)
            self._cam.start()
            self._fps = 30.0
            self._frame_size = (1280, 720)
            self._cam.set_controls(CAMERA_CONTROLS)

            # Hardware H.264 encoder runs continuously, keeping the last
            # PRE_BUFFER_SECONDS of footage in a ring buffer. Recording a
            # clip is just dumping that buffer to a file — near-zero CPU.
            from picamera2.encoders import H264Encoder
            from picamera2.outputs import CircularOutput
            self._encoder = H264Encoder(bitrate=6_000_000)
            self._circular = CircularOutput(
                buffersize=int(self._fps * PRE_BUFFER_SECONDS)
            )
            self._cam.start_encoder(self._encoder, self._circular)
            print("[camera] Started")
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

    def apply_controls(self, controls: dict):
        if _USE_PICAMERA and self._cam:
            self._cam.set_controls(controls)

    def read_frame(self):
        """Return the latest frame, or None on read failure."""
        if _USE_PICAMERA:
            return self._cam.capture_array("main")
        ret, frame = self._cam.read()
        return frame if ret else None

    def detect_motion(self, frame):
        """Background-subtraction motion check within the ROI of a downscaled frame.

        The ROI restricts detection to the feeder, ignoring background
        foliage so wind in trees doesn't false-trigger.
        """
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = MOTION_ROI
        roi = frame[int(y1 * h):int(y2 * h), int(x1 * w):int(x2 * w)]
        small = cv2.resize(roi, None, fx=self._motion_scale, fy=self._motion_scale,
                           interpolation=cv2.INTER_AREA)
        fg_mask = self.bg_subtractor.apply(small)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self._kernel)
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return any(cv2.contourArea(c) >= self._min_area for c in contours)

    def start_clip(self, path):
        """Dump the H.264 ring buffer (pre-roll) and keep writing to `path`."""
        if _USE_PICAMERA and self._circular:
            self._circular.fileoutput = path
            self._circular.start()

    def stop_clip(self):
        """Stop writing the current clip; the encoder keeps ring-buffering."""
        if _USE_PICAMERA and self._circular:
            self._circular.stop()

    def fps(self):
        return self._fps

    def frame_size(self):
        return self._frame_size

    def close(self):
        if self._cam:
            if _USE_PICAMERA:
                if self._circular:
                    try:
                        self._circular.stop()
                    except Exception:
                        pass
                if self._encoder:
                    self._cam.stop_encoder()
                self._cam.stop()
            else:
                self._cam.release()
