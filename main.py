import signal
import time
from concurrent.futures import ThreadPoolExecutor
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


BIRD_ID_ENABLED = False


def _classify_and_notify(snapshot: str):
    if BIRD_ID_ENABLED:
        print(f"Classifying {snapshot}...")
        species, confidence = classify_bird(snapshot)
        print(f"Result: {species} ({confidence}%)")
    else:
        species, confidence = "Motion detected", 0.0
    send_notification(snapshot, species, confidence)
    print("Telegram notification sent.")


def main():
    signal.signal(signal.SIGINT, _handle_sigint)

    detector = MotionDetector()
    detector.open()

    recorder = Recorder(fps=detector.fps(), frame_size=detector.frame_size())

    streamer.set_detector(detector)
    print(f"Stream available at http://localhost:{STREAM_PORT}")
    streamer.start()

    last_notification_time = 0.0
    last_mode_check_time = 0.0
    frame_count = 0

    print("Watching for movement. Press Ctrl+C to stop.")
    with ThreadPoolExecutor(max_workers=2) as pool:
        while _running:
            frame, motion = detector.read_frame()
            frame_count += 1
            if frame is None:
                print("Camera read failed — retrying...")
                time.sleep(0.1)
                continue

            streamer.update_frame(frame)
            recorder.push_frame(frame)

            now = time.time()
            cooldown_elapsed = (now - last_notification_time) >= NOTIFICATION_COOLDOWN

            if now - last_mode_check_time >= 60:
                detector.apply_mode_if_changed()
                last_mode_check_time = now

            if motion and frame_count % 10 == 0 and not recorder.is_recording() and cooldown_elapsed:
                print("Motion detected — saving clip + snapshot")
                recorder.trigger(frame)

            snapshot = recorder.snapshot_path()
            if snapshot and not recorder.is_recording() and cooldown_elapsed:
                last_notification_time = now
                recorder._snapshot_path = None
                pool.submit(_classify_and_notify, snapshot)

    detector.close()
    recorder.close()


if __name__ == "__main__":
    main()
