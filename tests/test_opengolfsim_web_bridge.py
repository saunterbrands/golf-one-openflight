"""Tests for the backend-owned OpenGolfSim Web API bridge."""

import json
import queue
import threading
import time

from simple_websocket import ConnectionClosed

from openflight.launch_monitor import ClubType
from openflight.opengolfsim.web_bridge import (
    OpenGolfSimWebBridge,
    WebBridgeState,
    build_web_shot_frame,
    open_golf_sim_websocket_url,
)
from openflight.sim.types import ResolvedShot


def _resolved(**overrides) -> ResolvedShot:
    values = {
        "shot_number": 42,
        "ball_speed_mph": 140.04,
        "vla": 12.44,
        "hla": -1.54,
        "total_spin_rpm": 2450.4,
        "spin_axis_deg": -3.24,
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


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached before timeout")


class FakeWebSocket:
    """Controllable, thread-safe WebSocket double."""

    def __init__(self):
        self.sent = []
        self.closed = False
        self.fail_next_send = False
        self.receive_events = queue.Queue()
        self._send_lock = threading.Lock()
        self.concurrent_sends = 0
        self.max_concurrent_sends = 0

    def send(self, data):
        with self._send_lock:
            if self.closed or self.fail_next_send:
                self.fail_next_send = False
                raise ConnectionClosed(1006, "closed")
            self.concurrent_sends += 1
            self.max_concurrent_sends = max(self.max_concurrent_sends, self.concurrent_sends)
        time.sleep(0.001)
        with self._send_lock:
            self.sent.append(data)
            self.concurrent_sends -= 1

    def receive(self, timeout=None):
        try:
            event = self.receive_events.get(timeout=timeout)
        except queue.Empty:
            if self.closed:
                raise ConnectionClosed(1000, "closed")
            return None
        if isinstance(event, Exception):
            raise event
        return event

    def close(self, reason=None, message=None):
        del reason, message
        self.closed = True

    def server_close(self, reason, message):
        self.receive_events.put(ConnectionClosed(reason, message))


class FakeWebSocketFactory:
    def __init__(self, *outcomes):
        self._outcomes = queue.Queue()
        for outcome in outcomes:
            self._outcomes.put(outcome)
        self.urls = []
        self._lock = threading.Lock()

    def __call__(self, url):
        with self._lock:
            self.urls.append(url)
        outcome = self._outcomes.get_nowait()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_url_percent_encodes_trimmed_email():
    assert (
        open_golf_sim_websocket_url(" player+test@example.com ")
        == "wss://app.opengolfsim.com/api/player%2Btest%40example.com"
    )


def test_build_web_shot_frame_uses_imperial_and_inverts_spin_axis():
    assert json.loads(build_web_shot_frame(_resolved())) == {
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


def test_start_opens_one_socket_and_announces_device_ready():
    websocket = FakeWebSocket()
    factory = FakeWebSocketFactory(websocket)
    statuses = []
    bridge = OpenGolfSimWebBridge(
        email="golfer@example.com",
        status_callback=statuses.append,
        websocket_factory=factory,
        reconnect_backoff=(0.01,),
        receive_timeout_s=0.01,
    )
    try:
        bridge.start()
        bridge.start()
        _wait_until(bridge.is_connected)

        assert factory.urls == ["wss://app.opengolfsim.com/api/golfer%40example.com"]
        assert json.loads(websocket.sent[0]) == {"type": "device", "status": "ready"}
        assert statuses[-1].state == WebBridgeState.CONNECTED
    finally:
        bridge.stop()


def test_send_shot_serializes_concurrent_writes():
    websocket = FakeWebSocket()
    bridge = OpenGolfSimWebBridge(
        email="golfer@example.com",
        websocket_factory=FakeWebSocketFactory(websocket),
        reconnect_backoff=(0.01,),
        receive_timeout_s=0.01,
    )
    try:
        bridge.start()
        _wait_until(bridge.is_connected)
        threads = [
            threading.Thread(target=bridge.send_shot, args=(_resolved(),)) for _ in range(20)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        shot_frames = [json.loads(frame) for frame in websocket.sent[1:]]
        assert len(shot_frames) == 20
        assert all(frame["shot"]["spinAxis"] == 3.2 for frame in shot_frames)
        assert websocket.max_concurrent_sends == 1
    finally:
        bridge.stop()


def test_transient_connect_failure_reconnects():
    websocket = FakeWebSocket()
    factory = FakeWebSocketFactory(OSError("offline"), websocket)
    statuses = []
    bridge = OpenGolfSimWebBridge(
        email="golfer@example.com",
        status_callback=statuses.append,
        websocket_factory=factory,
        reconnect_backoff=(0.01,),
        receive_timeout_s=0.01,
    )
    try:
        bridge.start()
        _wait_until(bridge.is_connected)

        assert len(factory.urls) == 2
        assert any(
            status.state == WebBridgeState.RECONNECTING and status.next_retry_in_s == 0.01
            for status in statuses
        )
    finally:
        bridge.stop()


def test_transient_socket_close_reconnects():
    first = FakeWebSocket()
    second = FakeWebSocket()
    factory = FakeWebSocketFactory(first, second)
    bridge = OpenGolfSimWebBridge(
        email="golfer@example.com",
        websocket_factory=factory,
        reconnect_backoff=(0.01,),
        receive_timeout_s=0.01,
    )
    try:
        bridge.start()
        _wait_until(bridge.is_connected)
        first.server_close(1006, "network lost")
        _wait_until(lambda: len(factory.urls) == 2 and bridge.is_connected())

        assert first.closed
        assert json.loads(second.sent[0]) == {"type": "device", "status": "ready"}
    finally:
        bridge.stop()


def test_transient_shot_send_failure_reconnects_without_queueing_stale_shot():
    first = FakeWebSocket()
    second = FakeWebSocket()
    factory = FakeWebSocketFactory(first, second)
    bridge = OpenGolfSimWebBridge(
        email="golfer@example.com",
        websocket_factory=factory,
        reconnect_backoff=(0.01,),
        receive_timeout_s=0.01,
    )
    try:
        bridge.start()
        _wait_until(bridge.is_connected)
        first.fail_next_send = True

        assert not bridge.send_shot(_resolved())
        _wait_until(lambda: len(factory.urls) == 2 and bridge.is_connected())
        assert len(second.sent) == 1  # Device-ready only; the failed shot is not replayed.
    finally:
        bridge.stop()


def test_invalid_user_is_permanent_until_email_is_configured_again():
    invalid = FakeWebSocket()
    recovered = FakeWebSocket()
    factory = FakeWebSocketFactory(invalid, recovered)
    statuses = []
    bridge = OpenGolfSimWebBridge(
        email="wrong@example.com",
        status_callback=statuses.append,
        websocket_factory=factory,
        reconnect_backoff=(0.01,),
        receive_timeout_s=0.01,
    )
    try:
        bridge.start()
        _wait_until(bridge.is_connected)
        invalid.server_close(1008, "Invalid User")
        _wait_until(lambda: bridge.status.state == WebBridgeState.INVALID_USER)
        time.sleep(0.03)

        assert len(factory.urls) == 1
        assert bridge.status.permanent
        assert bridge.status.message == "Invalid User"
        assert statuses[-1].state == WebBridgeState.INVALID_USER

        bridge.configure_email("right@example.com")
        _wait_until(lambda: bridge.is_connected() and len(factory.urls) == 2)
        assert factory.urls[-1].endswith("/right%40example.com")
    finally:
        bridge.stop()


def test_start_without_email_waits_until_configured():
    websocket = FakeWebSocket()
    factory = FakeWebSocketFactory(websocket)
    bridge = OpenGolfSimWebBridge(
        websocket_factory=factory,
        reconnect_backoff=(0.01,),
        receive_timeout_s=0.01,
    )
    try:
        bridge.start()
        _wait_until(lambda: bridge.status.state == WebBridgeState.UNCONFIGURED)
        assert factory.urls == []
        assert not bridge.send_shot(_resolved())

        bridge.configure_email("golfer@example.com")
        _wait_until(bridge.is_connected)
        assert len(factory.urls) == 1
    finally:
        bridge.stop()


def test_stop_prevents_reconnect_and_reports_stopped():
    websocket = FakeWebSocket()
    factory = FakeWebSocketFactory(websocket)
    bridge = OpenGolfSimWebBridge(
        email="golfer@example.com",
        websocket_factory=factory,
        reconnect_backoff=(0.01,),
        receive_timeout_s=0.01,
    )
    bridge.start()
    _wait_until(bridge.is_connected)

    bridge.stop()
    time.sleep(0.03)

    assert websocket.closed
    assert len(factory.urls) == 1
    assert bridge.status.state == WebBridgeState.STOPPED
