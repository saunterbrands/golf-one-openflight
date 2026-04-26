"""Connection lifecycle tests: state machine, reconnect, backoff."""
import time

from openflight.gspro.client import GSProClient
from openflight.gspro.config import GSProConfig
from openflight.gspro.state import ConnectionState


def _config(host, port, **overrides):
    base = dict(enabled=True, host=host, port=port, device_id="OpenFlight",
                units="Yards", heartbeat_interval_s=60)
    base.update(overrides)
    return GSProConfig(**base)


def _wait_until_state(client, target, deadline_s=3.0):
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        if client.state == target:
            return True
        time.sleep(0.05)
    return False


def test_start_transitions_to_connected(mock_gspro):
    client = GSProClient(_config(mock_gspro.host, mock_gspro.port))
    statuses = []
    client.on_status = statuses.append
    client.start()
    try:
        assert _wait_until_state(client, ConnectionState.CONNECTED)
        assert any(s.state == ConnectionState.CONNECTED for s in statuses)
    finally:
        client.stop()
    assert _wait_until_state(client, ConnectionState.STOPPED)


def test_reconnect_after_server_drop(mock_gspro):
    client = GSProClient(_config(mock_gspro.host, mock_gspro.port,
                                 heartbeat_interval_s=60),
                         backoff_seconds=(0.1, 0.2, 0.4))
    client.start()
    try:
        assert _wait_until_state(client, ConnectionState.CONNECTED)
        mock_gspro.disconnect_client()
        # should pass through RECONNECT_BACKOFF and back to CONNECTED
        assert _wait_until_state(client, ConnectionState.RECONNECT_BACKOFF, deadline_s=2.0)
        assert _wait_until_state(client, ConnectionState.CONNECTED, deadline_s=3.0)
    finally:
        client.stop()


def test_backoff_progression_capped():
    """Backoff schedule used when reconnecting hits a closed port."""
    cfg = GSProConfig(enabled=True, host="127.0.0.1", port=1,  # refused
                      device_id="OpenFlight", units="Yards",
                      heartbeat_interval_s=60)
    client = GSProClient(cfg, backoff_seconds=(0.05, 0.1, 0.1))
    statuses = []
    client.on_status = statuses.append
    client.start()
    time.sleep(0.5)
    client.stop()
    backoffs = [s.next_retry_in_s for s in statuses
                if s.state == ConnectionState.RECONNECT_BACKOFF]
    # Should see at least two backoff entries (initial + one retry)
    assert len(backoffs) >= 2
    # Capped at the last value in our schedule (0.1)
    assert max(backoffs) <= 0.1


def test_stop_is_idempotent(mock_gspro):
    client = GSProClient(_config(mock_gspro.host, mock_gspro.port))
    client.start()
    _wait_until_state(client, ConnectionState.CONNECTED)
    client.stop()
    client.stop()  # should not raise
    assert client.state == ConnectionState.STOPPED
