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

NOTIFICATION_COOLDOWN = int(os.getenv("NOTIFICATION_COOLDOWN", 30))

PRE_BUFFER_SECONDS = int(os.getenv("PRE_BUFFER_SECONDS", 3))
POST_TRIGGER_SECONDS = int(os.getenv("POST_TRIGGER_SECONDS", 7))

STREAM_PORT = int(os.getenv("STREAM_PORT", 5000))

CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)

HF_MODEL_URL = "https://api-inference.huggingface.co/models/chriamue/bird-species-classifier"
