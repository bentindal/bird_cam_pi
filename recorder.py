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
        self._clip_dir = None
        self._clip_h264 = None
        self._clip_mp4 = None
        self._bbox = None
        self._timer = None

    def trigger(self, frame, bbox=None):
        """Call when motion is detected: start a clip.

        The snapshot and classifier crop are taken from the *middle* of the
        finished clip (in _finalise), so they catch the settled bird rather
        than the trigger-instant transient. `frame` is saved as a provisional
        fallback snapshot in case the clip can't be processed.
        """
        if self._recording:
            return
        self._recording = True
        self._clip_mp4 = None
        self._bbox = bbox

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._clip_dir = os.path.join(CAPTURES_DIR, ts)
        os.makedirs(self._clip_dir, exist_ok=True)

        # Provisional snapshot from the trigger frame — replaced by a
        # mid-clip frame in _finalise() once the clip has been recorded.
        self._snapshot_path = os.path.join(self._clip_dir, "snapshot.jpg")
        self._classify_path = self._snapshot_path
        cv2.imwrite(self._snapshot_path, frame)

        self._clip_h264 = os.path.join(self._clip_dir, "clip.h264")
        self._detector.start_clip(self._clip_h264)

        self._timer = threading.Timer(POST_TRIGGER_SECONDS, self._finalise)
        self._timer.daemon = True
        self._timer.start()

    def _finalise(self):
        self._detector.stop_clip()
        # Remux and pick the snapshot before clearing _recording, so all
        # paths are ready the moment the main loop sees recording finished.
        self._clip_mp4 = self._remux_to_mp4(self._clip_h264)
        self._extract_midframe()
        self._recording = False

    def _extract_midframe(self):
        """Replace the snapshot with a frame from the middle of the clip —
        the bird is settled and in shot there, not mid-transit — and re-crop
        it to the motion box for the classifier."""
        clip = self._clip_mp4
        if not clip or not clip.endswith(".mp4") or not os.path.exists(clip):
            return  # remux failed — keep the provisional trigger snapshot
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", clip],
                capture_output=True, text=True, check=True, timeout=10)
            mid = float(probe.stdout.strip()) / 2
            subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{mid:.2f}", "-i", clip,
                 "-vframes", "1", self._snapshot_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=True, timeout=20)
        except Exception as e:
            print(f"[recorder] mid-frame extract failed, kept trigger snapshot: {e}")
            return

        # Classify a crop at the motion box; fall back to the full frame if
        # the box is tiny (motion didn't localise a real subject).
        self._classify_path = self._snapshot_path
        if self._bbox is not None:
            img = cv2.imread(self._snapshot_path)
            if img is not None:
                x1, y1, x2, y2 = self._bbox
                crop = img[y1:y2, x1:x2]
                if crop.size and crop.shape[0] >= 96 and crop.shape[1] >= 96:
                    self._classify_path = os.path.join(self._clip_dir, "crop.jpg")
                    cv2.imwrite(self._classify_path, crop)

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
