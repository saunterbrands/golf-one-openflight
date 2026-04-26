"""Basic send/recv tests for GSProClient (uses start/stop lifecycle)."""
import json
import time

from openflight.gspro.client import GSProClient
from openflight.gspro.config import GSProConfig
from openflight.gspro.messages import build_heartbeat
from openflight.gspro.state import ConnectionState


def _config(host, port):
    return GSProConfig(enabled=True, host=host, port=port,
                       device_id="OpenFlight", units="Yards",
                       heartbeat_interval_s=60)


def _wait_for_state(client, state, deadline=3.0):
    end = time.time() + deadline
    while time.time() < end:
        if client.state == state:
            return True
        time.sleep(0.05)
    return False


def test_send_payload_arrives_at_server(mock_gspro):
    client = GSProClient(_config(mock_gspro.host, mock_gspro.port))
    client.start()
    try:
        assert _wait_for_state(client, ConnectionState.CONNECTED)
        payload = {"hello": "world", "n": 1}
        client.send_raw(json.dumps(payload).encode("utf-8"))
        deadline = time.time() + 1.0
        while time.time() < deadline and not mock_gspro.received:
            time.sleep(0.05)
        assert mock_gspro.received
        assert json.loads(mock_gspro.received[0]) == payload
    finally:
        client.stop()


def test_recv_response_dispatches_callback(mock_gspro):
    received = []
    client = GSProClient(_config(mock_gspro.host, mock_gspro.port),
                         on_response=received.append)
    mock_gspro.queue_reply({"Code": 200, "Message": "OK"})
    client.start()
    try:
        deadline = time.time() + 1.0
        while time.time() < deadline and not received:
            time.sleep(0.05)
        assert len(received) == 1
        assert received[0].Code == 200
    finally:
        client.stop()


def test_send_heartbeat_helper(mock_gspro):
    client = GSProClient(_config(mock_gspro.host, mock_gspro.port))
    client.start()
    try:
        assert _wait_for_state(client, ConnectionState.CONNECTED)
        client.send_raw(build_heartbeat("OpenFlight", "Yards", shot_number=42))
        deadline = time.time() + 1.0
        while time.time() < deadline and not mock_gspro.received:
            time.sleep(0.05)
        assert mock_gspro.received
        obj = json.loads(mock_gspro.received[0])
        assert obj["ShotDataOptions"]["IsHeartBeat"] is True
    finally:
        client.stop()
