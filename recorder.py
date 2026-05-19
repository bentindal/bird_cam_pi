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
        self._clip_mp4 = None
        self._timer = None

    def trigger(self, frame, bbox=None):
        """Call when motion is detected: save a snapshot and start a clip.

        `bbox` (x1, y1, x2, y2) is the motion region; a crop of it is saved
        for the classifier, so it sees the bird and not the whole feeder.
        """
        if self._recording:
            return
        self._recording = True
        self._clip_mp4 = None

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        clip_dir = os.path.join(CAPTURES_DIR, ts)
        os.makedirs(clip_dir, exist_ok=True)

        self._snapshot_path = os.path.join(clip_dir, "snapshot.jpg")
        cv2.imwrite(self._snapshot_path, frame)

        # Classify the motion crop — but if the box is tiny (motion didn't
        # localise a real subject), fall back to the full snapshot.
        self._classify_path = self._snapshot_path
        if bbox is not None:
            x1, y1, x2, y2 = bbox
            crop = frame[y1:y2, x1:x2]
            if crop.shape[0] >= 96 and crop.shape[1] >= 96:
                self._classify_path = os.path.join(clip_dir, "crop.jpg")
                cv2.imwrite(self._classify_path, crop)

        self._clip_h264 = os.path.join(clip_dir, "clip.h264")
        self._detector.start_clip(self._clip_h264)

        self._timer = threading.Timer(POST_TRIGGER_SECONDS, self._finalise)
        self._timer.daemon = True
        self._timer.start()

    def _finalise(self):
        self._detector.stop_clip()
        # Remux before clearing _recording, so clip_path() is ready the
        # moment the main loop sees recording has finished.
        self._clip_mp4 = self._remux_to_mp4(self._clip_h264)
        self._recording = False

    @staticmethod
    def _remux_to_mp4(h264_path):
        """Wrap raw H.264 into .mp4 — a stream copy, no re-encoding.

        Returns the .mp4 path, or the .h264 path if the remux failed.
        """
        if not h264_path or not os.path.exists(h264_path):
            return None
        mp4_path = h264_path[:-5] + ".mp4"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-r", "30", "-i", h264_path, "-c", "copy", mp4_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=True, timeout=30,
            )
            os.remove(h264_path)
            return mp4_path
        except Exception as e:
            print(f"[recorder] mp4 remux skipped, kept .h264: {e}")
            return h264_path

    def snapshot_path(self):
        return self._snapshot_path

    def classify_path(self):
        """The image the classifier should use — the motion crop if available."""
        return self._classify_path

    def clip_path(self):
        """The finished clip (.mp4, or .h264 if the remux failed), or None."""
        return self._clip_mp4

    def is_recording(self):
        return self._recording

    def close(self):
        if self._timer:
            self._timer.cancel()
        if self._recording:
            self._detector.stop_clip()
            self._recording = False
