import asyncio
import sys
from datetime import datetime
from telegram import Bot
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

_VIDEO_EXTS = (".mp4", ".h264")


async def _send(media_path: str, species: str, confidence: float):
    bot = Bot(token=TELEGRAM_TOKEN)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    caption = (
        f"Bird detected!\n"
        f"Species: {species}\n"
        f"Time: {timestamp}\n"
        f"Confidence: {confidence}%"
    )
    with open(media_path, "rb") as f:
        if media_path.lower().endswith(_VIDEO_EXTS):
            await bot.send_video(
                chat_id=TELEGRAM_CHAT_ID, video=f, caption=caption,
                supports_streaming=True, write_timeout=120,
            )
        else:
            await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=f, caption=caption)


def send_notification(media_path: str, species: str, confidence: float):
    """Send a Telegram alert — a video clip if `media_path` is .mp4/.h264,
    otherwise a photo."""
    asyncio.run(_send(media_path, species, confidence))


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python notifier.py <media_path> [species] [confidence]")
        sys.exit(1)
    species = sys.argv[2] if len(sys.argv) > 2 else "Test Bird"
    confidence = float(sys.argv[3]) if len(sys.argv) > 3 else 99.0
    send_notification(path, species, confidence)
    print("Notification sent.")
