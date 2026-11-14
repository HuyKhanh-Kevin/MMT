"""Support both Heartbeat and heartbeat imports without Windows filename collisions."""
import sys
from . import Heartbeat as _heartbeat

sys.modules[__name__ + ".heartbeat"] = _heartbeat
