import signal
import time
from concurrent.futures import ThreadPoolExecutor
from detector import MotionDetector
from recorder import Recorder
from classifier import classify_bird
from notifier import send_notification
import streamer
from config import NOTIFICATION_COOLDOWN, STREAM_PORT, CONFIDENCE_THRESHOLD

_running = True


def _handle_sigint(sig, frame):
    global _running
    print("\nShutting down...")
    _running = False


BIRD_ID_ENABLED = True


def _classify_and_notify(snapshot: str):
    if BIRD_ID_ENABLED:
        print(f"Classifying {snapshot}...")
        species, confidence = classify_bird(snapshot)
        print(f"Result: {species} ({confidence}%)")
        if confidence < CONFIDENCE_THRESHOLD:
            print(f"Confidence below {CONFIDENCE_THRESHOLD}% — skipping notification.")
            return
    else:
        species, confidence = "Motion detected", 0.0
    send_notification(snapshot, species, confidence)
    print("Telegram notification sent.")


def main():
    signal.signal(signal.SIGINT, _handle_sigint)

    detector = MotionDetector()
    detector.open()

    recorder = Recorder(detector)

    streamer.set_detector(detector)
    print(f"Stream available at http://localhost:{STREAM_PORT}")
    streamer.start()

    last_notification_time = 0.0
    frame_count = 0

    # The hardware encoder records clips independently at full camera fps,
    # so this loop only needs frames for the preview stream and motion
    # detection — pace it well below the camera rate to save CPU.
    LOOP_INTERVAL = 1.0 / 15

    print("Watching for movement. Press Ctrl+C to stop.")
    with ThreadPoolExecutor(max_workers=2) as pool:
        while _running:
            loop_start = time.time()
            frame = detector.read_frame()
            frame_count += 1
            if frame is None:
                print("Camera read failed — retrying...")
                time.sleep(0.1)
                continue

            streamer.update_frame(frame)

            now = time.time()
            cooldown_elapsed = (now - last_notification_time) >= NOTIFICATION_COOLDOWN

            # Motion detection is the heaviest per-frame cost — run it only
            # every 10th frame (the trigger never acted more often anyway).
            if frame_count % 10 == 0 and detector.detect_motion(frame):
                if not recorder.is_recording() and cooldown_elapsed:
                    print("Motion detected — saving clip + snapshot")
                    recorder.trigger(frame)

            snapshot = recorder.snapshot_path()
            if snapshot and not recorder.is_recording() and cooldown_elapsed:
                last_notification_time = now
                recorder._snapshot_path = None
                pool.submit(_classify_and_notify, snapshot)

            elapsed = time.time() - loop_start
            if elapsed < LOOP_INTERVAL:
                time.sleep(LOOP_INTERVAL - elapsed)

    detector.close()
    recorder.close()


if __name__ == "__main__":
    main()
