from datetime import datetime
from astral import LocationInfo
from astral.sun import sun
import pytz

_LONDON = LocationInfo(name="London", region="England", timezone="Europe/London", latitude=51.5074, longitude=-0.1278)
_TZ = pytz.timezone("Europe/London")

# Picamera2 control values for each mode
DAY_CONTROLS = {
    "AeEnable": True,
    "AwbEnable": True,
}

NIGHT_CONTROLS = {
    "AeEnable": False,
    "AwbEnable": False,
    "AnalogueGain": 8.0,
    "ExposureTime": 80000,  # 80ms — motion-tolerant but sensitive
    "ColourGains": (1.5, 1.5),
}


def is_night() -> bool:
    now = datetime.now(_TZ)
    s = sun(_LONDON.observer, date=now.date(), tzinfo=_TZ)
    return not (s["sunrise"] < now < s["sunset"])


def current_controls() -> dict:
    return NIGHT_CONTROLS if is_night() else DAY_CONTROLS


def mode_name() -> str:
    return "night" if is_night() else "day"
