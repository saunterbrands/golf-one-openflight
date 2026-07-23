"""OpenGolfSim native Developer API codec.

OpenGolfSim's current API accepts plain JSON objects on TCP port 3111. It is
not the GSPro/OpenConnect V1 envelope: shots use the documented ``type=shot``
shape and a launch monitor announces itself with a ``device=ready`` event.
"""

import json
from typing import List, Optional

from openflight.launch_monitor import ClubType
from openflight.sim.types import (
    InboundEvent,
    PlayerUpdate,
    ResolvedShot,
    ShotAck,
    SimError,
)

_OPENGOLFSIM_FIELDS = [
    "ball_speed",
    "vla",
    "hla",
    "total_spin",
    "spin_axis",
]

_MPH_TO_MPS = 0.44704

_OGS_CLUB_TO_OPENFLIGHT = {
    "D": ClubType.DRIVER,
    "DR": ClubType.DRIVER,
    "DRIVER": ClubType.DRIVER,
    "3W": ClubType.WOOD_3,
    "W3": ClubType.WOOD_3,
    "5W": ClubType.WOOD_5,
    "W5": ClubType.WOOD_5,
    "7W": ClubType.WOOD_7,
    "W7": ClubType.WOOD_7,
    "3H": ClubType.HYBRID_3,
    "H3": ClubType.HYBRID_3,
    "5H": ClubType.HYBRID_5,
    "H5": ClubType.HYBRID_5,
    "7H": ClubType.HYBRID_7,
    "H7": ClubType.HYBRID_7,
    "9H": ClubType.HYBRID_9,
    "H9": ClubType.HYBRID_9,
    "2I": ClubType.IRON_2,
    "I2": ClubType.IRON_2,
    "3I": ClubType.IRON_3,
    "I3": ClubType.IRON_3,
    "4I": ClubType.IRON_4,
    "I4": ClubType.IRON_4,
    "5I": ClubType.IRON_5,
    "I5": ClubType.IRON_5,
    "6I": ClubType.IRON_6,
    "I6": ClubType.IRON_6,
    "7I": ClubType.IRON_7,
    "I7": ClubType.IRON_7,
    "8I": ClubType.IRON_8,
    "I8": ClubType.IRON_8,
    "9I": ClubType.IRON_9,
    "I9": ClubType.IRON_9,
    "PW": ClubType.PW,
    "AW": ClubType.GW,
    "GW": ClubType.GW,
    "SW": ClubType.SW,
    "LW": ClubType.LW,
}


def _normalize_units(units: str) -> str:
    """Map the shared config vocabulary onto OpenGolfSim's API values."""
    normalized = units.strip().lower()
    if normalized in {"metric", "meter", "meters", "metre", "metres", "m"}:
        return "metric"
    return "imperial"


class OpenGolfSimCodec:
    """Serialize Golf One shots for OpenGolfSim's native JSON API."""

    name = "opengolfsim"

    def __init__(self, units: str = "imperial"):
        self.units = _normalize_units(units)

    def build_shot(self, resolved: ResolvedShot) -> bytes:
        ball_speed = resolved.ball_speed_mph
        if self.units == "metric":
            ball_speed *= _MPH_TO_MPS

        payload = {
            "type": "shot",
            "unit": self.units,
            "shot": {
                "ballSpeed": round(ball_speed, 1),
                "verticalLaunchAngle": round(resolved.vla, 1),
                "horizontalLaunchAngle": round(resolved.hla, 1),
                "spinSpeed": round(resolved.total_spin_rpm, 0),
                # Golf One: positive = fade/right, OpenGolfSim: negative = fade/right.
                "spinAxis": round(-resolved.spin_axis_deg, 1),
            },
        }
        return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")

    def parse_inbound(self, frame: bytes) -> List[InboundEvent]:
        try:
            payload = json.loads(frame.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid OpenGolfSim JSON") from exc

        if not isinstance(payload, dict):
            raise ValueError("OpenGolfSim frame must be a JSON object")

        event_type = payload.get("type")
        if event_type == "result":
            return [ShotAck(ok=True, message="Shot result received")]

        if event_type == "player":
            data = payload.get("data")
            club_data = data.get("club") if isinstance(data, dict) else None
            club_id = club_data.get("id") if isinstance(club_data, dict) else None
            club = (
                _OGS_CLUB_TO_OPENFLIGHT.get(str(club_id).strip().upper())
                if club_id is not None
                else None
            )
            return [PlayerUpdate(club=club)] if club is not None else []

        if event_type == "error":
            message = payload.get("message") or payload.get("error") or "OpenGolfSim error"
            return [SimError(message=str(message))]

        return []

    def heartbeat_bytes(self) -> Optional[bytes]:
        return None

    def on_connect_bytes(self) -> Optional[bytes]:
        payload = json.dumps(
            {"type": "device", "status": "ready"},
            separators=(",", ":"),
        )
        return (payload + "\n").encode("utf-8")

    def fields_for_target(self) -> List[str]:
        return list(_OPENGOLFSIM_FIELDS)
