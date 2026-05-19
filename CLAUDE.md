# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Bird Cam Pi — a Raspberry Pi bird feeder camera with motion detection, optional
bird species identification, Telegram notifications, and a live MJPEG stream.

- GitHub: https://github.com/bentindal/bird_cam_pi
- Hardware: Raspberry Pi 4 + Pi Camera Module 3 (IMX708)

## Deployment

The application is deployed and running on a remote Raspberry Pi as a systemd
service (`bird-cam.service`). The Pi is on the local network at
**`projectmochi.local`**.

- SSH in to operate it: `ssh pi@projectmochi.local`
- App lives at `/home/pi/bird_cam_pi` on the Pi
- Live stream: `http://projectmochi.local:5000`
- Service control: `sudo systemctl {status,restart} bird-cam`
- Logs: `sudo journalctl -u bird-cam -f`

This Mac repo is the development copy. Deploy changes by pushing to GitHub and
pulling on the Pi, then restarting the service.

## Architecture

`main.py` runs the loop: read frame → stream + buffer → on motion, record a
clip + snapshot → classify (optional) → send Telegram notification.

| File | Role |
|---|---|
| `main.py` | Main loop, threading, cooldown logic |
| `detector.py` | picamera2 / OpenCV capture + background-subtraction motion detection |
| `recorder.py` | Circular pre-buffer, clip + snapshot saving |
| `classifier.py` | Hugging Face bird species API, rate-limited (100 calls/hr) |
| `notifier.py` | Telegram photo + caption |
| `streamer.py` | Flask MJPEG stream + live camera controls UI |
| `night_mode.py` | Sunrise/sunset camera switching (London tz, `astral`) |
| `config.py` | Loads all settings from `.env` |

## Key facts

- `BIRD_ID_ENABLED` in `main.py` is `True` — species classification runs on
  each motion snapshot via the Hugging Face API.
- Camera is mounted upside down — frames are rotated 180°.
- `AwbMode` is set to `Daylight` to fix a blue tint on the IMX708.
- Config comes from `.env` (not committed); see `config.py` for variables and
  defaults. `captures/` is gitignored.
- Motion is only checked every 10 frames; notifications respect
  `NOTIFICATION_COOLDOWN`.

## Development

- Run locally: `python3 main.py` (set `CAMERA_SOURCE=0` in `.env` for a Mac webcam)
- Test classifier: `python3 classifier.py path/to/bird.jpg`
- Test notifier: `python3 notifier.py path/to/image.jpg "Robin" 91.5`
- On the Pi, install OpenCV via apt (`python3-opencv`) for best compatibility.
