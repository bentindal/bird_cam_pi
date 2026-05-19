import requests
import sys
import time
import threading
from collections import deque
from config import HF_API_KEY, HF_MODEL_URL

_RATE_LIMIT = 100
_WINDOW = 3600  # 1 hour in seconds
_call_times: deque = deque()
_lock = threading.Lock()


def _under_rate_limit() -> bool:
    now = time.time()
    with _lock:
        while _call_times and now - _call_times[0] > _WINDOW:
            _call_times.popleft()
        if len(_call_times) >= _RATE_LIMIT:
            return False
        _call_times.append(now)
        return True


def classify_bird(image_path: str) -> tuple[str, float]:
    """Return (species_label, confidence) for the top prediction, or ("Unknown", 0.0) on failure."""
    if not _under_rate_limit():
        print("[classifier] Rate limit reached (100/hr) — skipping")
        return "Unknown", 0.0

    headers = {"Content-Type": "image/jpeg"}
    if HF_API_KEY:
        headers["Authorization"] = f"Bearer {HF_API_KEY}"

    try:
        with open(image_path, "rb") as f:
            data = f.read()
    except Exception as e:
        print(f"[classifier] Could not read image: {e}")
        return "Unknown", 0.0

    # The HF serverless endpoint cold-starts (model loading), so the first
    # call after idle is slow — use a generous timeout and retry once.
    for attempt in (1, 2):
        try:
            response = requests.post(HF_MODEL_URL, headers=headers, data=data, timeout=30)
            response.raise_for_status()
            results = response.json()
            if isinstance(results, list) and results:
                top = results[0]
                label = top.get("label", "Unknown").replace("_", " ").title()
                score = round(top.get("score", 0.0) * 100, 1)
                return label, score
            return "Unknown", 0.0
        except Exception as e:
            print(f"[classifier] attempt {attempt} failed: {e}")
            if attempt == 1:
                time.sleep(3)
    return "Unknown", 0.0


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python classifier.py <image_path>")
        sys.exit(1)
    label, confidence = classify_bird(path)
    print(f"Species: {label}  Confidence: {confidence}%")
