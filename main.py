import signal
import sys
import time
from detector import MotionDetector
from recorder import Recorder
from classifier import classify_bird
from notifier import send_notification
import streamer
from config import NOTIFICATION_COOLDOWN, STREAM_PORT

_running = True


def _handle_sigint(sig, frame):
    global _running
    print("\nShutting down...")
    _running = False


def main():
    signal.signal(signal.SIGINT, _handle_sigint)

    detector = MotionDetector()
    detector.open()

    recorder = Recorder(fps=detector.fps(), frame_size=detector.frame_size())

    print(f"Stream available at http://localhost:{STREAM_PORT}")
    streamer.start()

    last_notification_time = 0.0

    print("Watching for movement. Press Ctrl+C to stop.")
    while _running:
        frame, motion = detector.read_frame()
        if frame is None:
            print("Camera read failed — retrying...")
            time.sleep(0.1)
            continue

        streamer.update_frame(frame)
        recorder.push_frame(frame)

        now = time.time()
        cooldown_elapsed = (now - last_notification_time) >= NOTIFICATION_COOLDOWN

        if motion and not recorder.is_recording() and cooldown_elapsed:
            print(f"Motion detected — saving clip + snapshot")
            recorder.trigger(frame)

        # Once a recording finishes (post-trigger done), classify and notify
        snapshot = recorder.snapshot_path()
        if snapshot and not recorder.is_recording() and cooldown_elapsed:
            last_notification_time = now
            recorder._snapshot_path = None  # consume so we don't re-notify

            print(f"Classifying {snapshot}...")
            species, confidence = classify_bird(snapshot)
            print(f"Result: {species} ({confidence}%)")

            if NOTIFICATION_COOLDOWN > 0:
                send_notification(snapshot, species, confidence)
                print("Telegram notification sent.")

    detector.close()
    recorder.close()


if __name__ == "__main__":
    main()
