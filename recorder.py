import os
import subprocess
import threading
import cv2
from datetime import datetime
from config import CAPTURES_DIR, POST_TRIGGER_SECONDS


class Recorder:
    """Saves a snapshot + an H.264 clip when motion triggers.

    Video is encoded by the Pi's hardware H.264 encoder via the camera's
    CircularOutput (set up in MotionDetector), so the pre-roll is held in
    the encoder's ring buffer and recording costs almost no CPU here.
    """

    def __init__(self, detector):
        self._detector = detector
        self._recording = False
        self._snapshot_path = None
        self._classify_path = None
        self._clip_h264 = None
        self._timer = None

    def trigger(self, frame, bbox=None):
        """Call when motion is detected: save a snapshot and start a clip.

        `bbox` (x1, y1, x2, y2) is the motion region; a crop of it is saved
        for the classifier, so it sees the bird and not the whole feeder.
        """
        if self._recording:
            return
        self._recording = True

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        clip_dir = os.path.join(CAPTURES_DIR, ts)
        os.makedirs(clip_dir, exist_ok=True)

        self._snapshot_path = os.path.join(clip_dir, "snapshot.jpg")
        cv2.imwrite(self._snapshot_path, frame)

        if bbox is not None:
            x1, y1, x2, y2 = bbox
            crop = frame[y1:y2, x1:x2]
            self._classify_path = os.path.join(clip_dir, "crop.jpg")
            cv2.imwrite(self._classify_path, crop)
        else:
            self._classify_path = self._snapshot_path

        self._clip_h264 = os.path.join(clip_dir, "clip.h264")
        self._detector.start_clip(self._clip_h264)

        self._timer = threading.Timer(POST_TRIGGER_SECONDS, self._finalise)
        self._timer.daemon = True
        self._timer.start()

    def _finalise(self):
        self._detector.stop_clip()
        self._recording = False
        self._remux_to_mp4(self._clip_h264)

    @staticmethod
    def _remux_to_mp4(h264_path):
        """Wrap raw H.264 into .mp4 — a stream copy, no re-encoding."""
        if not h264_path or not os.path.exists(h264_path):
            return
        mp4_path = h264_path[:-5] + ".mp4"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-r", "30", "-i", h264_path, "-c", "copy", mp4_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=True, timeout=30,
            )
            os.remove(h264_path)
        except Exception as e:
            print(f"[recorder] mp4 remux skipped, kept .h264: {e}")

    def snapshot_path(self):
        return self._snapshot_path

    def classify_path(self):
        """The image the classifier should use — the motion crop if available."""
        return self._classify_path

    def is_recording(self):
        return self._recording

    def close(self):
        if self._timer:
            self._timer.cancel()
        if self._recording:
            self._detector.stop_clip()
            self._recording = False
