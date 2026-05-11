import threading
import cv2
from flask import Flask, Response
from config import STREAM_PORT

app = Flask(__name__)
_latest_frame = None
_lock = threading.Lock()


def update_frame(frame):
    global _latest_frame
    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    with _lock:
        _latest_frame = jpeg.tobytes()


def _generate():
    while True:
        with _lock:
            frame = _latest_frame
        if frame:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


@app.route("/stream")
def stream():
    return Response(_generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/")
def index():
    return '<html><body><img src="/stream" style="max-width:100%"></body></html>'


def start(daemon=True):
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=STREAM_PORT, threaded=True), daemon=daemon)
    t.start()
    return t
