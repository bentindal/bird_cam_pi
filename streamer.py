import json
import os
import threading
import time
from datetime import datetime
import cv2
from flask import Flask, Response, request, jsonify, send_from_directory
from config import STREAM_PORT, MOTION_ROI, MOTION_ROI_OVERLAY, CAPTURES_DIR

app = Flask(__name__)

# Cap the MJPEG encode rate — smooth enough for a bird cam, and far cheaper
# than JPEG-encoding every camera frame.
_STREAM_FPS = 12
_STREAM_INTERVAL = 1.0 / _STREAM_FPS

_latest_jpeg = None
_frame_version = 0
_last_encode = 0.0
_client_count = 0
_cond = threading.Condition()
_detector = None

AWB_MODES = {
    "auto": 0,
    "tungsten": 1,
    "fluorescent": 2,
    "indoor": 3,
    "daylight": 4,
    "cloudy": 5,
}


def set_detector(detector):
    global _detector
    _detector = detector


def update_frame(frame):
    """Encode a frame for the stream.

    No-ops when nobody is watching, and throttles encoding to _STREAM_FPS,
    so an idle camera costs nothing and a watched one costs ~12 encodes/sec.
    """
    global _latest_jpeg, _frame_version, _last_encode
    if _client_count == 0:
        return
    now = time.monotonic()
    if now - _last_encode < _STREAM_INTERVAL:
        return
    if MOTION_ROI_OVERLAY:
        # Draw on a copy so the snapshot/clip frames stay unmarked.
        frame = frame.copy()
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = MOTION_ROI
        cv2.rectangle(frame, (int(x1 * w), int(y1 * h)),
                      (int(x2 * w), int(y2 * h)), (0, 255, 0), 2)
    ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if not ok:
        return
    with _cond:
        _last_encode = now
        _latest_jpeg = jpeg.tobytes()
        _frame_version += 1
        _cond.notify_all()


def _generate():
    """Yield each new frame exactly once, blocking until one is ready.

    Replaces a busy-wait loop that pinned a CPU core; this sleeps until
    update_frame() signals a new frame.
    """
    last_version = -1
    while True:
        with _cond:
            ready = _cond.wait_for(lambda: _frame_version != last_version, timeout=5.0)
            if not ready:
                continue
            frame = _latest_jpeg
            last_version = _frame_version
        if frame:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


@app.route("/stream")
def stream():
    def _tracked():
        global _client_count
        with _cond:
            _client_count += 1
        try:
            yield from _generate()
        finally:
            with _cond:
                _client_count -= 1
    return Response(_tracked(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/control/awb", methods=["POST"])
def set_awb():
    mode = request.json.get("mode", "auto").lower()
    if mode not in AWB_MODES:
        return jsonify({"error": f"Unknown mode. Options: {list(AWB_MODES)}"}), 400
    if _detector:
        _detector.apply_controls({"AwbEnable": True, "AwbMode": AWB_MODES[mode]})
    return jsonify({"ok": True, "awb": mode})


@app.route("/control/gains", methods=["POST"])
def set_gains():
    red = float(request.json.get("red", 2.0))
    blue = float(request.json.get("blue", 2.0))
    if _detector:
        _detector.apply_controls({"AwbEnable": False, "ColourGains": (red, blue)})
    return jsonify({"ok": True, "red": red, "blue": blue})


@app.route("/")
def index():
    return """<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { margin: 0; background: #111; color: #eee; font-family: sans-serif; }
    img { width: 100%; display: block; }
    .controls { padding: 12px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    button { padding: 8px 14px; border: none; border-radius: 6px; background: #333; color: #eee; cursor: pointer; font-size: 14px; }
    button:hover { background: #555; }
    button.active { background: #2a7; }
    .sep { width: 1px; height: 28px; background: #444; }
    input[type=range] { width: 120px; }
    label { font-size: 13px; }
  </style>
</head>
<body>
  <img src="/stream">
  <div class="controls">
    <span style="font-size:13px;color:#aaa">AWB:</span>
    <button onclick="setAwb('auto')">Auto</button>
    <button onclick="setAwb('daylight')" class="active">Daylight</button>
    <button onclick="setAwb('cloudy')">Cloudy</button>
    <button onclick="setAwb('indoor')">Indoor</button>
    <button onclick="setAwb('tungsten')">Tungsten</button>
    <button onclick="setAwb('fluorescent')">Fluorescent</button>
    <div class="sep"></div>
    <label>R <input type="range" id="red" min="1" max="4" step="0.1" value="2.0" oninput="setGains()"></label>
    <label>B <input type="range" id="blue" min="1" max="4" step="0.1" value="2.0" oninput="setGains()"></label>
    <button onclick="resetAwb()">Reset</button>
    <a href="/sightings" style="margin-left:auto;color:#2a7;font-size:14px;text-decoration:none;">&#128038; Sightings</a>
  </div>
  <script>
    function setAwb(mode) {
      fetch('/control/awb', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({mode})});
      document.querySelectorAll('button').forEach(b => b.classList.remove('active'));
      event.target.classList.add('active');
    }
    function setGains() {
      const red = parseFloat(document.getElementById('red').value);
      const blue = parseFloat(document.getElementById('blue').value);
      fetch('/control/gains', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({red, blue})});
    }
    function resetAwb() {
      fetch('/control/awb', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({mode:'daylight'})});
    }
  </script>
</body>
</html>"""


def _format_ts(name):
    try:
        return datetime.strptime(name, "%Y-%m-%d_%H-%M-%S").strftime("%-d %b · %H:%M:%S")
    except ValueError:
        return name


@app.route("/sightings")
@app.route("/captures")
def sightings_index():
    cards, count = [], 0
    for name in sorted(os.listdir(CAPTURES_DIR), reverse=True):
        d = os.path.join(CAPTURES_DIR, name)
        if not os.path.isdir(d):
            continue
        files = set(os.listdir(d))
        clip = next((f for f in ("clip.mp4", "clip.h264") if f in files), None)
        if "snapshot.jpg" not in files and not clip:
            continue
        count += 1

        species, confidence = "Unidentified", None
        if "sighting.json" in files:
            try:
                with open(os.path.join(d, "sighting.json")) as fh:
                    info = json.load(fh)
                species = info.get("species") or "Unidentified"
                confidence = info.get("confidence")
            except Exception:
                pass

        conf_html = ""
        if confidence is not None:
            tier = "hi" if confidence >= 70 else "mid" if confidence >= 40 else "lo"
            conf_html = f'<span class="conf {tier}">{confidence:.0f}%</span>'
        badge = "🎬 Video" if clip else "📷 Photo"
        href = f"/captures/{name}/{clip}" if clip else f"/captures/{name}/snapshot.jpg"
        thumb = (f'<img src="/captures/{name}/snapshot.jpg" loading="lazy" alt="">'
                 if "snapshot.jpg" in files else '<div class="noimg">🐦</div>')
        cards.append(
            f'<a class="card" href="{href}">'
            f'<div class="thumb">{thumb}<span class="badge">{badge}</span></div>'
            f'<div class="info"><div class="species">{species}{conf_html}</div>'
            f'<div class="when">{_format_ts(name)}</div></div></a>'
        )
    body = "".join(cards) or '<p class="empty">No sightings yet — waiting for a visitor 🐦</p>'
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bird Sightings</title>
<style>
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:#15171a; color:#e8e6e1;
         font-family:-apple-system,Segoe UI,Roboto,sans-serif; }}
  header {{ position:sticky; top:0; display:flex; align-items:center; gap:12px;
           padding:14px 18px; background:#1d2024; border-bottom:1px solid #2c3036; }}
  header h1 {{ font-size:19px; margin:0; }}
  .count {{ background:#2e7d52; color:#fff; font-size:13px; font-weight:600;
           padding:2px 10px; border-radius:999px; }}
  .live {{ margin-left:auto; color:#7fd4a8; text-decoration:none; font-size:14px; }}
  .grid {{ display:grid; gap:14px; padding:16px;
          grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); }}
  .card {{ background:#1d2024; border-radius:14px; overflow:hidden;
          text-decoration:none; color:inherit; border:1px solid #2c3036;
          transition:transform .12s ease, box-shadow .12s ease; }}
  .card:hover {{ transform:translateY(-3px); box-shadow:0 8px 22px #0008; }}
  .thumb {{ position:relative; aspect-ratio:16/9; background:#101214; }}
  .thumb img {{ width:100%; height:100%; object-fit:cover; display:block; }}
  .noimg {{ display:flex; align-items:center; justify-content:center;
           height:100%; font-size:38px; }}
  .badge {{ position:absolute; bottom:8px; right:8px; background:#000a;
           font-size:12px; padding:3px 8px; border-radius:8px; }}
  .info {{ padding:10px 12px 12px; }}
  .species {{ font-size:16px; font-weight:600; display:flex;
             align-items:center; gap:8px; }}
  .conf {{ font-size:12px; font-weight:700; padding:2px 8px; border-radius:999px; }}
  .conf.hi {{ background:#2e7d52; color:#fff; }}
  .conf.mid {{ background:#b8860b; color:#fff; }}
  .conf.lo {{ background:#7a3b3b; color:#fff; }}
  .when {{ font-size:12.5px; color:#9aa0a8; margin-top:4px; }}
  .empty {{ padding:48px 20px; text-align:center; color:#9aa0a8; font-size:15px; }}
</style></head><body>
<header><h1>🐦 Bird Sightings</h1><span class="count">{count}</span>
<a class="live" href="/">● Live stream</a></header>
<div class="grid">{body}</div>
</body></html>"""


@app.route("/captures/<path:relpath>")
def captures_file(relpath):
    return send_from_directory(CAPTURES_DIR, relpath)


def start(daemon=True):
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=STREAM_PORT, threaded=True), daemon=daemon)
    t.start()
    return t
