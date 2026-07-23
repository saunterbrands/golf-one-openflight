"""Tests for OpenGolfSim's documented native Developer API wire format."""

import json

import pytest

from openflight.launch_monitor import ClubType
from openflight.opengolfsim.codec import OpenGolfSimCodec
from openflight.sim.types import PlayerUpdate, ResolvedShot, ShotAck, SimError


def _resolved(**overrides) -> ResolvedShot:
    values = {
        "shot_number": 42,
        "ball_speed_mph": 140.0,
        "vla": 12.4,
        "hla": -1.5,
        "total_spin_rpm": 2450.0,
        "spin_axis_deg": -3.2,
        "back_spin_rpm": 2446.2,
        "side_spin_rpm": -136.8,
        "carry_yards": 255.0,
        "club_path_deg": 0.5,
        "club": ClubType.DRIVER,
        "club_speed_mph": 109.0,
        "provenance": {},
    }
    values.update(overrides)
    return ResolvedShot(**values)


def test_build_shot_uses_native_developer_api_payload():
    frame = OpenGolfSimCodec().build_shot(_resolved())
    payload = json.loads(frame)

    assert frame.endswith(b"\n")
    assert payload == {
        "type": "shot",
        "unit": "imperial",
        "shot": {
            "ballSpeed": 140.0,
            "verticalLaunchAngle": 12.4,
            "horizontalLaunchAngle": -1.5,
            "spinSpeed": 2450.0,
            "spinAxis": 3.2,
        },
    }
    assert "DeviceID" not in payload
    assert "BallData" not in payload


def test_metric_units_are_normalized_for_native_api():
    payload = json.loads(OpenGolfSimCodec(units="Meters").build_shot(_resolved()))
    assert payload["unit"] == "metric"
    assert payload["shot"]["ballSpeed"] == 62.6


@pytest.mark.parametrize(
    ("golf_one_axis", "ogs_axis"),
    [
        pytest.param(8.5, -8.5, id="fade"),
        pytest.param(-8.5, 8.5, id="draw"),
    ],
)
def test_spin_axis_is_converted_to_opengolfsim_convention(golf_one_axis, ogs_axis):
    payload = json.loads(OpenGolfSimCodec().build_shot(_resolved(spin_axis_deg=golf_one_axis)))
    assert payload["shot"]["spinAxis"] == ogs_axis


def test_on_connect_marks_the_launch_monitor_ready():
    frame = OpenGolfSimCodec().on_connect_bytes()
    assert frame is not None
    assert frame.endswith(b"\n")
    payload = json.loads(frame)
    assert payload == {"type": "device", "status": "ready"}


def test_native_api_does_not_send_openconnect_heartbeats():
    assert OpenGolfSimCodec().heartbeat_bytes() is None


def test_parse_result_as_shot_ack():
    events = OpenGolfSimCodec().parse_inbound(
        json.dumps(
            {
                "type": "result",
                "data": {"result": {"carry": 196.1, "total": 202.5}},
            }
        ).encode()
    )
    assert events == [ShotAck(ok=True, message="Shot result received")]


@pytest.mark.parametrize(
    ("ogs_id", "club"),
    [
        ("DR", ClubType.DRIVER),
        ("5W", ClubType.WOOD_5),
        ("7I", ClubType.IRON_7),
        ("PW", ClubType.PW),
    ],
)
def test_parse_player_club_update(ogs_id, club):
    frame = json.dumps(
        {"type": "player", "data": {"club": {"id": ogs_id, "name": ogs_id}}}
    ).encode()
    assert OpenGolfSimCodec().parse_inbound(frame) == [PlayerUpdate(club=club)]


def test_parse_error_event():
    events = OpenGolfSimCodec().parse_inbound(
        json.dumps({"type": "error", "message": "Shot rejected"}).encode()
    )
    assert events == [SimError(message="Shot rejected")]


def test_parse_malformed_frame_raises_value_error():
    with pytest.raises(ValueError):
        OpenGolfSimCodec().parse_inbound(b"{not json")


def test_fields_match_what_opengolfsim_receives():
    assert OpenGolfSimCodec().fields_for_target() == [
        "ball_speed",
        "vla",
        "hla",
        "total_spin",
        "spin_axis",
    ]
