import cv2
import os
from collections import deque
from datetime import datetime
from config import CAPTURES_DIR, PRE_BUFFER_SECONDS, POST_TRIGGER_SECONDS


class Recorder:
    def __init__(self, fps, frame_size):
        self.fps = fps
        self.frame_size = frame_size
        pre_buffer_frames = int(PRE_BUFFER_SECONDS * fps)
        self.pre_buffer = deque(maxlen=pre_buffer_frames)
        self._writer = None
        self._post_frames_remaining = 0
        self._current_dir = None
        self._snapshot_path = None

    def push_frame(self, frame):
        """Always call with every frame. Handles pre-buffer and post-trigger recording."""
        self.pre_buffer.append(frame.copy())
        if self._writer and self._post_frames_remaining > 0:
            self._writer.write(frame)
            self._post_frames_remaining -= 1
            if self._post_frames_remaining == 0:
                self._finalise()

    def trigger(self, frame):
        """Call when motion is detected. Saves snapshot and starts clip recording."""
        if self._writer:
            return  # already recording
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._current_dir = os.path.join(CAPTURES_DIR, ts)
        os.makedirs(self._current_dir, exist_ok=True)

        self._snapshot_path = os.path.join(self._current_dir, "snapshot.jpg")
        cv2.imwrite(self._snapshot_path, frame)

        clip_path = os.path.join(self._current_dir, "clip.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(clip_path, fourcc, self.fps, self.frame_size)

        for buffered in self.pre_buffer:
            self._writer.write(buffered)

        self._post_frames_remaining = int(POST_TRIGGER_SECONDS * self.fps)

    def snapshot_path(self):
        return self._snapshot_path

    def is_recording(self):
        return self._writer is not None

    def _finalise(self):
        self._writer.release()
        self._writer = None

    def close(self):
        if self._writer:
            self._writer.release()
