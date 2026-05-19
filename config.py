import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HF_API_KEY = os.getenv("HF_API_KEY")

CAMERA_SOURCE = os.getenv("CAMERA_SOURCE", "0")
CAMERA_SOURCE = int(CAMERA_SOURCE) if CAMERA_SOURCE.isdigit() else CAMERA_SOURCE

MOTION_THRESHOLD = int(os.getenv("MOTION_THRESHOLD", 500))
MIN_CONTOUR_AREA = int(os.getenv("MIN_CONTOUR_AREA", 1500))
# Reject motion blobs larger than this fraction of the ROI — a real bird
# never fills most of the feeder; feeder sway / lighting changes do.
MOTION_MAX_AREA_FRAC = float(os.getenv("MOTION_MAX_AREA_FRAC", 0.6))

NOTIFICATION_COOLDOWN = int(os.getenv("NOTIFICATION_COOLDOWN", 30))

# Minimum bird-ID confidence (%) required to send a Telegram notification.
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", 60))

# Species to never notify about — the classifier always returns *some* bird,
# so birdless frames get a confident wrong guess. Comma-separated, matched
# case-insensitively against the classifier label.
IGNORED_SPECIES = {
    s.strip().lower()
    for s in os.getenv("IGNORED_SPECIES", "").split(",")
    if s.strip()
}

PRE_BUFFER_SECONDS = int(os.getenv("PRE_BUFFER_SECONDS", 3))
POST_TRIGGER_SECONDS = int(os.getenv("POST_TRIGGER_SECONDS", 7))

STREAM_PORT = int(os.getenv("STREAM_PORT", 5000))

CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)

HF_MODEL_URL = "https://router.huggingface.co/hf-inference/models/chriamue/bird-species-classifier"


def _parse_roi(raw):
    """Parse 'x1,y1,x2,y2' normalized (0-1) coords; fall back to the whole frame."""
    try:
        vals = tuple(float(v) for v in raw.split(","))
        if len(vals) == 4 and all(0.0 <= v <= 1.0 for v in vals):
            return vals
    except ValueError:
        pass
    return (0.0, 0.0, 1.0, 1.0)


# Motion detection region of interest — restricts detection to the feeder,
# ignoring background foliage (wind in trees is a major false-trigger source).
# Normalized (0-1) "x1,y1,x2,y2"; default estimates the feeder box.
MOTION_ROI = _parse_roi(os.getenv("MOTION_ROI", "0.18,0.48,0.84,1.0"))
# Draw the ROI box on the live stream so it can be fine-tuned visually.
MOTION_ROI_OVERLAY = os.getenv("MOTION_ROI_OVERLAY", "true").lower() == "true"
