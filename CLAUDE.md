# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Bird Cam Pi — a Raspberry Pi bird feeder camera with motion detection, optional
bird species identification, Telegram notifications, and a live MJPEG stream.

- GitHub: https://github.com/bentindal/bird_cam_pi
- Hardware: Raspberry Pi 4 + Pi Camera Module 3 (IMX708)

## Deployment

The application is deployed and running on a remote Raspberry Pi as a systemd
service (`bird-cam.service`).

- Local network: `projectmochi.local` (mDNS)
- Tailscale: hostname `projectmochi`, IP `100.86.62.4` — reachable from anywhere
  on the tailnet (`tailscaled` is installed and enabled on boot)
- Tailscale MagicDNS: `projectmochi.tailbcba89.ts.net`
- SSH user is `mochi`: `ssh mochi@100.86.62.4` (or `ssh mochi@projectmochi`)
- App lives at `/home/mochi/bird_cam_pi` on the Pi
- Live stream: `http://projectmochi.tailbcba89.ts.net:5000`
  (or `http://projectmochi:5000` / `http://100.86.62.4:5000`)
- Service control: `sudo systemctl {status,restart} bird-cam`
- Logs: `sudo journalctl -u bird-cam -f`

This Mac repo is the development copy. Deploy changes by pushing to GitHub and
pulling on the Pi, then restarting the service.

## Architecture

`main.py` runs the loop: read frame → stream → on motion, trigger a clip +
snapshot → classify (optional) → send Telegram notification.

| File | Role |
|---|---|
| `main.py` | Main loop, threading, cooldown logic, loop pacing |
| `detector.py` | picamera2 / OpenCV capture, motion detection, hardware encoder lifecycle |
| `recorder.py` | Snapshot + clip orchestration (drives the hardware encoder) |
| `classifier.py` | Hugging Face bird species API, rate-limited (100 calls/hr) |
| `notifier.py` | Telegram photo + caption |
| `streamer.py` | Flask MJPEG stream + live camera controls UI |
| `config.py` | Loads all settings from `.env` |

### Video pipeline (hardware-encoded)

Clips are encoded by the Pi 4's **hardware H.264 encoder**, not the CPU:

- `detector.py` configures the camera at 30fps and starts a picamera2
  `H264Encoder` + `CircularOutput`. The encoder runs continuously in
  silicon, ring-buffering the last `PRE_BUFFER_SECONDS` of footage.
- On motion, `recorder.trigger()` saves a snapshot and calls
  `detector.start_clip()` — which just dumps the ring buffer to a file and
  keeps writing. A `threading.Timer` calls `detector.stop_clip()` after
  `POST_TRIGGER_SECONDS`.
- Raw `.h264` is remuxed to `.mp4` via an ffmpeg stream-copy (no re-encode).
- The 180° flip (camera mounted upside down) is done by the ISP via a
  libcamera `Transform` — free, no per-frame CPU.
- The main loop only needs frames for the preview stream and motion
  detection, so it is **paced to 15fps** while the camera/encoder run at
  30fps. Clip quality is decoupled from loop CPU cost.

This keeps the Pi at ~48% CPU / ~56°C whether idle or recording. Earlier
software encoding (`cv2.VideoWriter`) spiked CPU ~60% and overheated the Pi.

## Key facts

- `BIRD_ID_ENABLED` in `main.py` is `True` — species classification runs on
  each motion snapshot via the Hugging Face API.
- Camera mounted upside down — flipped in the ISP (`Transform`), not on CPU.
- Fixed camera controls live in `detector.py` `CAMERA_CONTROLS` —
  `AwbMode: 5` (Daylight) corrects the IMX708's blue tint. There is no
  day/night switching; the camera runs one fixed profile.
- Clip recording requires the picamera2 path (the hardware encoder). On a
  Mac webcam (`CAMERA_SOURCE=0`), snapshots/notifications work but clips do not.
- Config comes from `.env` (not committed); see `config.py` for variables and
  defaults. `captures/` is gitignored.
- Motion is checked every 10th loop iteration; notifications respect
  `NOTIFICATION_COOLDOWN`.
- Motion detection is restricted to a **region of interest** (`MOTION_ROI` in
  `.env`, normalized `x1,y1,x2,y2`) covering the feeder, so wind in background
  foliage doesn't false-trigger. The ROI box is drawn on the live stream
  (`MOTION_ROI_OVERLAY`) for visual tuning.
- Telegram notifications are only sent when bird-ID confidence exceeds
  `CONFIDENCE_THRESHOLD` (default 60%) and the species is not in
  `IGNORED_SPECIES` (the classifier always returns *some* bird, so
  birdless frames get a confident wrong guess — e.g. "wood duck").

## Development

- Run locally: `python3 main.py` (set `CAMERA_SOURCE=0` in `.env` for a Mac webcam)
- Test classifier: `python3 classifier.py path/to/bird.jpg`
- Test notifier: `python3 notifier.py path/to/image.jpg "Robin" 91.5`
- On the Pi, install OpenCV via apt (`python3-opencv`) for best compatibility.
