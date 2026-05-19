import cv2
import numpy as np
from config import (CAMERA_SOURCE, MOTION_THRESHOLD, MIN_CONTOUR_AREA,
                    PRE_BUFFER_SECONDS, MOTION_ROI, MOTION_MAX_AREA_FRAC)

_USE_PICAMERA = CAMERA_SOURCE == "picamera"


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
            # No forced white balance — the camera runs its own auto AWB.

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
        """Detect bird-plausible motion within the feeder ROI.

        Returns the full-frame bounding box (x1, y1, x2, y2) of the moving
        subject — padded slightly for context — or None. Blobs that are too
        small (sensor noise) or too large (feeder sway, lighting changes)
        are rejected, so only bird-sized motion triggers a capture.
        """
        h, w = frame.shape[:2]
        rx1, ry1 = int(MOTION_ROI[0] * w), int(MOTION_ROI[1] * h)
        rx2, ry2 = int(MOTION_ROI[2] * w), int(MOTION_ROI[3] * h)
        roi = frame[ry1:ry2, rx1:rx2]
        small = cv2.resize(roi, None, fx=self._motion_scale, fy=self._motion_scale,
                           interpolation=cv2.INTER_AREA)
        fg_mask = self.bg_subtractor.apply(small)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self._kernel)
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        max_area = small.shape[0] * small.shape[1] * MOTION_MAX_AREA_FRAC
        candidates = [c for c in contours
                      if self._min_area <= cv2.contourArea(c) <= max_area]
        if not candidates:
            return None

        bx, by, bw, bh = cv2.boundingRect(max(candidates, key=cv2.contourArea))
        s = self._motion_scale
        # small -> ROI -> full frame, then pad 30% for context, clamped.
        fx1, fy1 = rx1 + bx / s, ry1 + by / s
        fx2, fy2 = rx1 + (bx + bw) / s, ry1 + (by + bh) / s
        pad_x, pad_y = (fx2 - fx1) * 0.3, (fy2 - fy1) * 0.3
        return (max(0, int(fx1 - pad_x)), max(0, int(fy1 - pad_y)),
                min(w, int(fx2 + pad_x)), min(h, int(fy2 + pad_y)))

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
