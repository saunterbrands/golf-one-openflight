"""Integration: two connectors (GSPro + OpenGolfSim) running concurrently.

Both ride the shared OpenConnect V1 codec; they differ only in target/name. The
shot must reach each connector's own endpoint independently.
"""
import json
import time
from datetime import datetime

from openflight.launch_monitor import ClubType, Shot
from openflight.sim.codec import build_connectors
from openflight.sim.config import ConnectorConfig
from openflight.sim.resolver import resolve_shot
from openflight.sim.transport import find_json_end
from openflight.sim.types import ConnectionState, PlayerState
from tests.conftest import MockSimServer


def _wait(connector, state, deadline=3.0):
    end = time.time() + deadline
    while time.time() < end:
        if connector.state == state:
            return True
        time.sleep(0.05)
    return False


def _frames(received_chunks):
    """Concatenate received bytes and split into individual JSON objects."""
    buf = b"".join(received_chunks)
    out = []
    while True:
        end = find_json_end(buf)
        if end is None:
            break
        out.append(json.loads(buf[:end]))
        buf = buf[end:]
    return out


def test_shot_reaches_both_sims():
    gspro_srv = MockSimServer()
    ogs_srv = MockSimServer()
    try:
        cfgs = [
            ConnectorConfig(type="gspro", enabled=True, host=gspro_srv.host,
                            port=gspro_srv.port),
            ConnectorConfig(type="opengolfsim", enabled=True, host=ogs_srv.host,
                            port=ogs_srv.port),
        ]
        connectors = build_connectors(cfgs)
        assert {c.name for c in connectors} == {"gspro", "opengolfsim"}
        for c in connectors:
            c.start()
        try:
            assert all(_wait(c, ConnectionState.CONNECTED) for c in connectors)

            shot = Shot(ball_speed_mph=135.0, timestamp=datetime(2026, 6, 13, 12, 0, 0),
                        club=ClubType.DRIVER, launch_angle_vertical=11.1,
                        launch_angle_horizontal=1.2)
            resolved = resolve_shot(shot, PlayerState())
            for c in connectors:
                c.send_shot(resolved)

            deadline = time.time() + 1.5
            while time.time() < deadline and not (gspro_srv.received and ogs_srv.received):
                time.sleep(0.05)

            # Both speak OpenConnect V1 — each endpoint gets the BallData shot.
            for srv in (gspro_srv, ogs_srv):
                shot_msg = next(m for m in _frames(srv.received) if "BallData" in m)
                assert shot_msg["BallData"]["Speed"] == 135.0
                assert shot_msg["APIversion"] == "1"
        finally:
            for c in connectors:
                c.stop()
    finally:
        gspro_srv.stop()
        ogs_srv.stop()
