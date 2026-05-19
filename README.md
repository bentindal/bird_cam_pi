# Bird Cam Pi

Raspberry Pi bird feeder camera with motion detection, automatic bird species identification, and Telegram notifications.

## Features

- **Motion detection** — OpenCV background subtraction, restricted to a configurable region of interest
- **Clip + snapshot recording** — hardware-encoded H.264 clips (3s pre-buffer + 7s post-trigger) saved locally
- **Bird species ID** — Hugging Face inference API (`chriamue/bird-species-classifier`), capped at 100 calls/hour
- **Telegram alerts** — photo, species name, confidence score, and timestamp sent to your phone (only above a confidence threshold)
- **Live MJPEG stream** — viewable in any browser at `http://<pi-ip>:5000`
- **Runs as a systemd service** — starts on boot, restarts automatically on crash

## Hardware

- Raspberry Pi 4
- Pi Camera Module 3 (IMX708)

> **Night vision note:** The IMX708 has an IR cut filter. For visibility after dark you'll need an external IR illuminator (850nm LED board) or swap to the Pi Camera Module 3 NoIR.

## Project Structure

```
bird_cam_pi/
├── main.py          — main loop: motion → record → classify → notify
├── detector.py      — picamera2 / OpenCV capture, motion detection, hardware encoder
├── recorder.py      — snapshot + clip orchestration (hardware H.264 encoder)
├── classifier.py    — Hugging Face bird species API with rate limiting
├── notifier.py      — Telegram photo + caption
├── streamer.py      — MJPEG HTTP stream via Flask
├── config.py        — loads all settings from .env
├── captures/        — saved clips and snapshots (gitignored)
└── .env.example     — config template
```

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/bentindal/bird_cam_pi.git
cd bird_cam_pi
pip3 install -r requirements.txt
```

On Raspberry Pi, install OpenCV via apt for best compatibility:

```bash
sudo apt-get install -y python3-opencv
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
HF_API_KEY=your_huggingface_api_key

CAMERA_SOURCE=picamera   # or 0 for Mac webcam
NOTIFICATION_COOLDOWN=10
```

**Getting a Telegram bot:**
1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token
2. Message your new bot, then message [@userinfobot](https://t.me/userinfobot) to get your chat ID

**Hugging Face API key:** Free account at [huggingface.co](https://huggingface.co) — works without a key at low usage.

### 3. Run

```bash
python3 main.py
```

Open `http://localhost:5000` in a browser to see the live stream.

## Raspberry Pi: Run as a service

```bash
sudo tee /etc/systemd/system/bird-cam.service > /dev/null << 'EOF'
[Unit]
Description=Bird Cam
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/bird_cam_pi
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable bird-cam
sudo systemctl start bird-cam
```

View logs:

```bash
sudo journalctl -u bird-cam -f
```

## Testing individual components

```bash
# Test bird classifier with an image
python3 classifier.py path/to/bird.jpg

# Send a test Telegram notification
python3 notifier.py path/to/image.jpg "Robin" 91.5
```

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `CAMERA_SOURCE` | `0` | `picamera` for Pi Camera, `0` for webcam |
| `MOTION_THRESHOLD` | `500` | Background subtractor sensitivity (lower = more sensitive) |
| `MIN_CONTOUR_AREA` | `1500` | Minimum pixel area to count as motion |
| `NOTIFICATION_COOLDOWN` | `10` | Seconds between Telegram notifications |
| `PRE_BUFFER_SECONDS` | `3` | Seconds of footage saved before trigger |
| `POST_TRIGGER_SECONDS` | `7` | Seconds of footage saved after trigger |
| `STREAM_PORT` | `5000` | HTTP stream port |
