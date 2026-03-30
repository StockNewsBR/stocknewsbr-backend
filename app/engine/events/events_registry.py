from .volume_explosion import detect_volume_explosion
from .fake_breakout import detect_fake_breakout
from .trend_acceleration import detect_trend_acceleration

EVENTS = [
    detect_volume_explosion,
    detect_fake_breakout,
    detect_trend_acceleration,
]