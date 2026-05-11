import asyncio
import sys
from datetime import datetime
from telegram import Bot
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID


async def _send(image_path: str, species: str, confidence: float):
    bot = Bot(token=TELEGRAM_TOKEN)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    caption = (
        f"Bird detected!\n"
        f"Species: {species}\n"
        f"Time: {timestamp}\n"
        f"Confidence: {confidence}%"
    )
    with open(image_path, "rb") as photo:
        await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=photo, caption=caption)


def send_notification(image_path: str, species: str, confidence: float):
    asyncio.run(_send(image_path, species, confidence))


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python notifier.py <image_path> [species] [confidence]")
        sys.exit(1)
    species = sys.argv[2] if len(sys.argv) > 2 else "Test Bird"
    confidence = float(sys.argv[3]) if len(sys.argv) > 3 else 99.0
    send_notification(path, species, confidence)
    print("Notification sent.")
