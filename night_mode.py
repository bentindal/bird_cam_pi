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
    "AwbMode": 5,  # Daylight (AwbModeEnum) — corrects the IMX708's cool/blue bias
}

NIGHT_CONTROLS = {
    "AeEnable": False,
    "AwbEnable": False,
    "AnalogueGain": 16.0,    # max analogue gain
    "ExposureTime": 200000,  # 200ms — slow but maximally sensitive
    "ColourGains": (2.0, 2.0),
}


def is_night() -> bool:
    now = datetime.now(_TZ)
    s = sun(_LONDON.observer, date=now.date(), tzinfo=_TZ)
    return not (s["sunrise"] < now < s["sunset"])


def current_controls() -> dict:
    return NIGHT_CONTROLS if is_night() else DAY_CONTROLS


def mode_name() -> str:
    return "night" if is_night() else "day"
