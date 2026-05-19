import threading
import time
import cv2
from flask import Flask, Response, request, jsonify
from config import STREAM_PORT, MOTION_ROI, MOTION_ROI_OVERLAY

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


def start(daemon=True):
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=STREAM_PORT, threaded=True), daemon=daemon)
    t.start()
    return t
