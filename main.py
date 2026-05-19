import signal
import time
from concurrent.futures import ThreadPoolExecutor
from detector import MotionDetector
from recorder import Recorder
from classifier import classify_bird
from notifier import send_notification
import streamer
from config import NOTIFICATION_COOLDOWN, STREAM_PORT, MOTION_CONSECUTIVE

_running = True


def _handle_sigint(sig, frame):
    global _running
    print("\nShutting down...")
    _running = False


BIRD_ID_ENABLED = True


def _classify_and_notify(clip: str, snapshot: str, classify_img: str):
    if BIRD_ID_ENABLED:
        print(f"Classifying {classify_img}...")
        species, confidence = classify_bird(classify_img)
        print(f"Result: {species} ({confidence}%)")
    else:
        species, confidence = "Motion detected", 0.0
    media = clip if clip else snapshot
    send_notification(media, species, confidence)
    print(f"Telegram notification sent ({'clip' if clip else 'snapshot'}).")


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
    motion_streak = 0

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
            # Require sustained motion across several detection cycles
            # before recording — lets a bird land and settle, and rejects
            # brief transient motion.
            if frame_count % 10 == 0:
                bbox = detector.detect_motion(frame)
                motion_streak = motion_streak + 1 if bbox else 0
                if (motion_streak >= MOTION_CONSECUTIVE
                        and not recorder.is_recording() and cooldown_elapsed):
                    print("Sustained motion — recording clip + snapshot")
                    recorder.trigger(frame, bbox)
                    motion_streak = 0

            snapshot = recorder.snapshot_path()
            if snapshot and not recorder.is_recording() and cooldown_elapsed:
                last_notification_time = now
                classify_img = recorder.classify_path()
                clip = recorder.clip_path()
                recorder._snapshot_path = None
                pool.submit(_classify_and_notify, clip, snapshot, classify_img)

            elapsed = time.time() - loop_start
            if elapsed < LOOP_INTERVAL:
                time.sleep(LOOP_INTERVAL - elapsed)

    detector.close()
    recorder.close()


if __name__ == "__main__":
    main()
