"""Server-side registry wiring: shot fan-out and inbound handling.

Exercises server._forward_shot_to_simulators and server._sim_on_inbound with
fake connectors so no sockets or hardware are needed.
"""

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from openflight.launch_monitor import ClubType, Shot
from openflight.opengolfsim.browser_relay import BrowserShotRelay
from openflight.sim.types import ConnectionState, PlayerUpdate, ShotAck, SimError

_EXTENSION_HEADERS = {
    "Origin": "chrome-extension://golf-one-test",
    "X-Golf-One-Extension": "browser-relay-v1",
}


class _FakeWebBridge:
    def __init__(self):
        self.email = ""
        self.sent = []
        self.send_result = True
        self.started = False
        self.status = SimpleNamespace(
            state=SimpleNamespace(value="unconfigured"),
            message="Enter the OpenGolfSim account email to connect",
            attempt=0,
            next_retry_in_s=0.0,
            permanent=False,
        )

    def configure_email(self, email):
        self.email = email
        self.status = SimpleNamespace(
            state=SimpleNamespace(value="connecting" if email else "unconfigured"),
            message="Connecting to OpenGolfSim" if email else "Enter the account email",
            attempt=1 if email else 0,
            next_retry_in_s=0.0,
            permanent=False,
        )

    def set_status_callback(self, _callback, replay=True):
        del replay

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def send_shot(self, resolved):
        if self.send_result:
            self.sent.append(resolved)
        return self.send_result


@pytest.fixture
def server(monkeypatch):
    """Import the server module with socketio.emit and session logger stubbed."""
    import openflight.server as srv

    emitted = []
    monkeypatch.setattr(srv.socketio, "emit", lambda *a, **k: emitted.append((a, k)))
    monkeypatch.setattr(srv, "get_session_logger", lambda: None)
    srv._emitted = emitted  # convenience handle for assertions
    # Reset shared state between tests
    srv.sim_connectors = []
    srv.sim_player_state = srv.SimPlayerState()
    fake_web_bridge = _FakeWebBridge()
    monkeypatch.setattr(srv, "opengolfsim_web_bridge", fake_web_bridge)
    srv._fake_web_bridge = fake_web_bridge
    browser_relay = BrowserShotRelay(poll_timeout_s=0.001)
    monkeypatch.setattr(srv, "opengolfsim_browser_relay", browser_relay)
    srv._browser_relay = browser_relay
    yield srv
    # Don't leak fake connectors / player state into other test modules
    # (server.on_shot_detected reads these globals).
    srv.sim_connectors = []
    srv.sim_player_state = srv.SimPlayerState()


class _FakeConnector:
    def __init__(self, name, connected=True):
        self.name = name
        self.codec = type("C", (), {"fields_for_target": lambda self: ["ball_speed", "vla"]})()
        self._connected = connected
        self.sent = []
        self.host = "127.0.0.1"
        self.port = 921
        self.state = ConnectionState.CONNECTED if connected else ConnectionState.RECONNECT_BACKOFF

    def is_connected(self):
        return self._connected

    def send_shot(self, resolved):
        self.sent.append(resolved)


def _shot():
    return Shot(
        ball_speed_mph=140.0,
        timestamp=datetime(2026, 6, 13, 12, 0, 0),
        club=ClubType.DRIVER,
        launch_angle_vertical=12.0,
    )


def test_forward_fans_out_to_connected_only(server):
    a = _FakeConnector("gspro", connected=True)
    b = _FakeConnector("opengolfsim", connected=False)
    server.sim_connectors = [a, b]

    server._forward_shot_to_simulators(_shot())

    assert len(a.sent) == 1
    assert len(b.sent) == 0
    # sim_shot emitted once for the connected connector
    shots = [a_ for a_, k in server._emitted if a_[0] == "sim_shot"]
    assert len(shots) == 1
    assert shots[0][1]["target"] == "gspro"


def test_forward_allocates_one_shot_number_across_connectors(server):
    a = _FakeConnector("gspro")
    b = _FakeConnector("opengolfsim")
    server.sim_connectors = [a, b]

    server._forward_shot_to_simulators(_shot())

    assert a.sent[0].shot_number == b.sent[0].shot_number == 1


def test_forward_noop_when_no_connector_connected(server):
    server.sim_connectors = [_FakeConnector("gspro", connected=False)]
    server._forward_shot_to_simulators(_shot())
    # No shot number consumed while offline.
    assert server.sim_player_state.shot_counter == 0
    assert not any(a_[0] == "sim_shot" for a_, k in server._emitted)


def test_forward_sends_one_shot_through_device_owned_web_bridge(server):
    server._fake_web_bridge.configure_email("golfer@example.com")

    server._forward_shot_to_simulators(_shot())

    assert len(server._fake_web_bridge.sent) == 1
    assert server._fake_web_bridge.sent[0].ball_speed_mph == 140.0
    assert server.sim_player_state.shot_counter == 0
    web_shots = [
        args
        for args, _kwargs in server._emitted
        if args[0] == "sim_shot" and args[1]["target"] == "opengolfsim-web"
    ]
    assert len(web_shots) == 1
    assert web_shots[0][1]["fields"] == [
        "ball_speed",
        "vla",
        "hla",
        "total_spin",
        "spin_axis",
    ]


def test_forward_prefers_live_browser_game_without_requiring_account_email(server):
    session = server._browser_relay.open_session()

    server._forward_shot_to_simulators(_shot())

    assert server._fake_web_bridge.sent == []
    deliveries = server._browser_relay.poll(
        session_id=session["session_id"],
        after=session["cursor"],
    )
    assert len(deliveries) == 1
    assert deliveries[0]["payload"]["shot"]["ballSpeed"] == 140.0
    local_shots = [
        args
        for args, _kwargs in server._emitted
        if args[0] == "sim_shot" and args[1]["delivery"] == "browser"
    ]
    assert len(local_shots) == 1


def test_forward_does_not_duplicate_live_browser_shot_over_cloud_bridge(server):
    server._fake_web_bridge.configure_email("golfer@example.com")
    session = server._browser_relay.open_session()

    server._forward_shot_to_simulators(_shot())

    assert server._fake_web_bridge.sent == []
    assert (
        len(
            server._browser_relay.poll(
                session_id=session["session_id"],
                after=session["cursor"],
            )
        )
        == 1
    )


def test_forward_reports_web_shot_lost_while_bridge_disconnected(server):
    server._fake_web_bridge.configure_email("golfer@example.com")
    server._fake_web_bridge.send_result = False

    server._forward_shot_to_simulators(_shot())

    failed = [
        args
        for args, _kwargs in server._emitted
        if args[0] == "sim_send_failed" and args[1]["target"] == "opengolfsim-web"
    ]
    assert len(failed) == 1


def test_opengolfsim_api_saves_account_and_starts_bridge(server, monkeypatch, tmp_path):
    config_path = tmp_path / "golf-one" / "opengolfsim.json"
    monkeypatch.setenv("GOLF_ONE_OPENGOLFSIM_CONFIG", str(config_path))
    client = server.app.test_client()

    initial = client.get("/api/opengolfsim")
    assert initial.status_code == 200
    assert initial.get_json()["configured"] is False

    response = client.post("/api/opengolfsim", json={"email": " golfer@example.com "})
    assert response.status_code == 200
    assert response.get_json()["configured"] is True
    assert response.get_json()["email"] == "golfer@example.com"
    assert server._fake_web_bridge.email == "golfer@example.com"
    assert server._fake_web_bridge.started
    assert config_path.read_text(encoding="utf-8") == '{\n  "email": "golfer@example.com"\n}\n'
    assert config_path.stat().st_mode & 0o777 == 0o600


def test_opengolfsim_browser_api_is_tokenized_and_loopback_only(server):
    client = server.app.test_client()

    opened = client.post(
        "/api/opengolfsim/browser/session",
        json={"state": "ready"},
        headers=_EXTENSION_HEADERS,
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert opened.status_code == 200
    session = opened.get_json()
    assert session["session_id"]
    assert session["cursor"] == 0

    polled = client.post(
        "/api/opengolfsim/browser/poll",
        json={"session_id": session["session_id"], "after": 0},
        headers=_EXTENSION_HEADERS,
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert polled.status_code == 200
    assert polled.get_json()["shots"] == []

    rejected = client.post(
        "/api/opengolfsim/browser/session",
        json={"state": "ready"},
        headers=_EXTENSION_HEADERS,
        environ_overrides={"REMOTE_ADDR": "192.168.0.55"},
    )
    assert rejected.status_code == 403


def test_opengolfsim_browser_api_rejects_invalid_session_token(server):
    response = server.app.test_client().post(
        "/api/opengolfsim/browser/poll",
        json={"session_id": "wrong", "after": 0},
        headers=_EXTENSION_HEADERS,
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == "OpenGolfSim browser session is no longer active"


def test_opengolfsim_browser_test_shot_reaches_active_mock_game(server, monkeypatch):
    monitor = server.MockLaunchMonitor()
    monitor.start(shot_callback=server._forward_shot_to_simulators)
    monkeypatch.setattr(server, "monitor", monitor)
    session = server._browser_relay.open_session()

    response = server.app.test_client().post(
        "/api/opengolfsim/browser/test-shot",
        headers=_EXTENSION_HEADERS,
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )

    assert response.status_code == 202
    delivery = server._browser_relay.poll(
        session_id=session["session_id"],
        after=session["cursor"],
    )
    assert delivery[0]["payload"]["shot"]["ballSpeed"] == 142.0


def test_opengolfsim_browser_api_rejects_untrusted_web_origin(server):
    response = server.app.test_client().post(
        "/api/opengolfsim/browser/session",
        json={"state": "ready"},
        headers={
            "Origin": "https://untrusted.example",
            "X-Golf-One-Extension": "browser-relay-v1",
        },
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )

    assert response.status_code == 403
    assert server._browser_relay.is_active() is False


@pytest.mark.parametrize("email", ["", "not-an-email", "two@@example.com", "space @example.com"])
def test_opengolfsim_api_rejects_invalid_account(server, email):
    response = server.app.test_client().post("/api/opengolfsim", json={"email": email})
    assert response.status_code == 400
    assert not server._fake_web_bridge.started


def test_display_mode_api_defaults_saves_and_reloads(server, monkeypatch, tmp_path):
    config_path = tmp_path / "golf-one" / "display.json"
    monkeypatch.setenv("GOLF_ONE_DISPLAY_CONFIG", str(config_path))
    client = server.app.test_client()

    initial = client.get("/api/display-mode")
    assert initial.status_code == 200
    assert initial.get_json() == {
        "mode": "simulator",
        "url": "https://app.opengolfsim.com/account/simulator",
    }

    saved = client.post("/api/display-mode", json={"mode": "launch_monitor"})
    assert saved.status_code == 200
    assert saved.get_json() == {"mode": "launch_monitor", "url": "/display"}
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"mode": "launch_monitor"}
    assert config_path.stat().st_mode & 0o777 == 0o600

    reloaded = client.get("/api/display-mode")
    assert reloaded.get_json() == {"mode": "launch_monitor", "url": "/display"}

    local_range = client.post("/api/display-mode", json={"mode": "practice_range"})
    assert local_range.status_code == 200
    assert local_range.get_json() == {
        "mode": "practice_range",
        "url": "/offline-simulator",
    }
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "mode": "practice_range"
    }

    online = client.post("/api/display-mode", json={"mode": "simulator"})
    assert online.status_code == 200
    assert online.get_json() == {
        "mode": "simulator",
        "url": "https://app.opengolfsim.com/account/simulator",
    }


def test_offline_fuse_runtime_reports_and_serves_installed_range(
    server, monkeypatch, tmp_path
):
    fuse_root = tmp_path / "fuse" / "current"
    range_dir = fuse_root / "examples" / "range"
    range_dir.mkdir(parents=True)
    (range_dir / "index.html").write_text(
        "<!doctype html><title>Local FUSE Range</title>",
        encoding="utf-8",
    )
    (fuse_root / "BUILD_VARIANT").write_text(
        "range-explicit-webgl-anisotropy4-v3\n",
        encoding="utf-8",
    )
    (fuse_root / "SOURCE_COMMIT").write_text(
        "6f10092c4444a538dd869d495eb2cb45697a5fb5\n",
        encoding="utf-8",
    )
    (fuse_root / "SOURCE_PATCH_SHA256").write_text(
        "4905d5f6823125fc96594f83f3880fab5b905448a7ada9cf12959d151dbbebc3\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GOLF_ONE_OFFLINE_FUSE_DIR", str(fuse_root))
    client = server.app.test_client()

    runtime = client.get("/api/opengolfsim/runtime")
    assert runtime.status_code == 200
    assert runtime.get_json() == {
        "online_url": "https://app.opengolfsim.com/account/simulator",
        "offline_url": "/offline-simulator",
        "offline_available": True,
        "offline_profile": "pi-balanced",
        "build_variant": "range-explicit-webgl-anisotropy4-v3",
        "source_commit": "6f10092c4444a538dd869d495eb2cb45697a5fb5",
        "source_patch_sha256": "4905d5f6823125fc96594f83f3880fab5b905448a7ada9cf12959d151dbbebc3",
    }

    wrapper = client.get("/offline-simulator")
    assert wrapper.status_code == 200
    wrapper_html = wrapper.get_data(as_text=True)
    assert 'title="fuse"' in wrapper_html
    assert 'src="/fuse/examples/range/index.html"' in wrapper_html
    assert 'type: "setup"' in wrapper_html
    assert "qualityLevel: 1" in wrapper_html
    assert 'name: "Golf One Player"' in wrapper_html

    asset = client.get("/fuse/examples/range/index.html")
    assert asset.status_code == 200
    assert "Local FUSE Range" in asset.get_data(as_text=True)
    assert (
        client.get("/fuse/BUILD_VARIANT").get_data(as_text=True).strip()
        == "range-explicit-webgl-anisotropy4-v3"
    )


def test_offline_fuse_runtime_fails_clearly_when_range_is_not_installed(
    server, monkeypatch, tmp_path
):
    monkeypatch.setenv(
        "GOLF_ONE_OFFLINE_FUSE_DIR",
        str(tmp_path / "missing-fuse"),
    )
    client = server.app.test_client()

    assert client.get("/api/opengolfsim/runtime").get_json() == {
        "online_url": "https://app.opengolfsim.com/account/simulator",
        "offline_url": "/offline-simulator",
        "offline_available": False,
        "offline_profile": None,
        "build_variant": None,
        "source_commit": None,
        "source_patch_sha256": None,
    }
    unavailable = client.get("/offline-simulator")
    assert unavailable.status_code == 503
    assert "Offline Practice Range is not installed" in unavailable.get_data(
        as_text=True
    )


def test_offline_fuse_runtime_ignores_missing_or_malformed_provenance(
    server, monkeypatch, tmp_path
):
    fuse_root = tmp_path / "fuse" / "current"
    range_dir = fuse_root / "examples" / "range"
    range_dir.mkdir(parents=True)
    (range_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (fuse_root / "BUILD_VARIANT").write_text("../../not-a-variant\n", encoding="utf-8")
    (fuse_root / "SOURCE_COMMIT").write_text("x" * 129, encoding="utf-8")
    monkeypatch.setenv("GOLF_ONE_OFFLINE_FUSE_DIR", str(fuse_root))

    runtime = server.app.test_client().get("/api/opengolfsim/runtime")

    assert runtime.status_code == 200
    assert runtime.get_json() == {
        "online_url": "https://app.opengolfsim.com/account/simulator",
        "offline_url": "/offline-simulator",
        "offline_available": True,
        "offline_profile": None,
        "build_variant": None,
        "source_commit": None,
        "source_patch_sha256": None,
    }


def test_simulator_launcher_prefers_official_login_and_falls_back_local(server):
    response = server.app.test_client().get("/simulator/launch")

    assert response.status_code == 200
    launcher = response.get_data(as_text=True)
    assert "https://app.opengolfsim.com/account/simulator" in launcher
    assert "/offline-simulator" in launcher
    assert "mode: 'no-cors'" in launcher


def test_display_mode_api_rejects_unknown_mode(server, monkeypatch, tmp_path):
    monkeypatch.setenv(
        "GOLF_ONE_DISPLAY_CONFIG",
        str(tmp_path / "golf-one" / "display.json"),
    )

    response = server.app.test_client().post(
        "/api/display-mode",
        json={"mode": "unsupported"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Choose a supported Golf One display."}


def test_display_mode_api_rejects_cross_origin_write(server, monkeypatch, tmp_path):
    config_path = tmp_path / "golf-one" / "display.json"
    monkeypatch.setenv("GOLF_ONE_DISPLAY_CONFIG", str(config_path))

    response = server.app.test_client().post(
        "/api/display-mode",
        json={"mode": "launch_monitor"},
        headers={"Origin": "https://unrelated.example"},
    )

    assert response.status_code == 403
    assert response.get_json() == {"error": "This display setting can only be changed on Golf One."}
    assert not config_path.exists()


def test_display_mode_api_allows_same_host_development_origin(server, monkeypatch, tmp_path):
    monkeypatch.setenv(
        "GOLF_ONE_DISPLAY_CONFIG",
        str(tmp_path / "golf-one" / "display.json"),
    )

    response = server.app.test_client().post(
        "/api/display-mode",
        json={"mode": "launch_monitor"},
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    assert response.get_json()["mode"] == "launch_monitor"


def test_forward_drops_shot_without_ball_speed(server):
    server.sim_connectors = [_FakeConnector("gspro")]
    bad = Shot(ball_speed_mph=0.0, timestamp=datetime(2026, 6, 13, 12, 0, 0), club=ClubType.DRIVER)
    server._forward_shot_to_simulators(bad)
    dropped = [a_ for a_, k in server._emitted if a_[0] == "sim_shot_dropped"]
    assert len(dropped) == 1


def test_inbound_player_update_sets_state_and_monitor(server, monkeypatch):
    set_clubs = []
    fake_monitor = type("M", (), {"set_club": lambda self, c: set_clubs.append(c)})()
    monkeypatch.setattr(server, "monitor", fake_monitor)

    server._sim_on_inbound("gspro", PlayerUpdate(handed="LH", club=ClubType.IRON_7))

    assert server.sim_player_state.handed == "LH"
    assert server.sim_player_state.club is ClubType.IRON_7
    assert set_clubs == [ClubType.IRON_7]
    players = [a_ for a_, k in server._emitted if a_[0] == "sim_player"]
    assert players and players[0][1]["club"] == ClubType.IRON_7.value


def test_inbound_error_emits_status(server):
    server._sim_on_inbound("opengolfsim", SimError(message="boom"))
    errs = [
        a_ for a_, k in server._emitted if a_[0] == "sim_status" and a_[1].get("state") == "error"
    ]
    assert errs and errs[0][1]["message"] == "boom"


def test_inbound_rejected_ack_is_tolerated(server):
    # Should not raise or emit; just informational.
    server._sim_on_inbound("gspro", ShotAck(shot_number=4, ok=False, message="nope"))


def test_send_logged_only_in_debug_mode(server, monkeypatch, caplog):
    server.sim_connectors = [_FakeConnector("gspro")]

    monkeypatch.setattr(server, "debug_mode", False)
    with caplog.at_level("INFO", logger="openflight.server"):
        server._forward_shot_to_simulators(_shot())
    assert "shot #1" not in caplog.text

    caplog.clear()
    monkeypatch.setattr(server, "debug_mode", True)
    with caplog.at_level("INFO", logger="openflight.server"):
        server._forward_shot_to_simulators(_shot())
    assert "gspro shot #2" in caplog.text


def test_player_update_logged_always(server, caplog):
    with caplog.at_level("INFO", logger="openflight.server"):
        server._sim_on_inbound("opengolfsim", PlayerUpdate(club=ClubType.IRON_7))
    assert "player update: club=" in caplog.text


def test_status_connected_logged_always(server, caplog):
    from openflight.sim.types import ConnectionState, StatusEvent

    with caplog.at_level("INFO", logger="openflight.server"):
        server._sim_on_status(
            "gspro",
            StatusEvent(
                state=ConnectionState.CONNECTED, target="gspro", host="127.0.0.1", port=921
            ),
        )
    assert "gspro connected" in caplog.text


def test_emit_sim_snapshot_sends_status_for_every_connector(server):
    # The UI builds connector buttons from sim_status events, which otherwise
    # only fire on state *changes*. A client that connects after a connector
    # already settled would miss the event and show no button — so the server
    # replays a snapshot on connect. Every enabled connector must get a
    # sim_status carrying its current state, regardless of what that state is.
    a = _FakeConnector("gspro", connected=True)
    b = _FakeConnector("opengolfsim", connected=False)
    b.state = ConnectionState.RECONNECT_BACKOFF
    server.sim_connectors = [a, b]

    server._emit_sim_snapshot()

    by_target = {a_[1]["target"]: a_[1] for a_, _k in server._emitted if a_[0] == "sim_status"}
    assert set(by_target) == {"gspro", "opengolfsim"}
    assert by_target["gspro"]["state"] == "connected"
    assert by_target["opengolfsim"]["state"] == "reconnecting"
    assert by_target["gspro"]["port"] == 921


def test_emit_sim_snapshot_noop_without_connectors(server):
    # No connectors configured (no --sim / none enabled) → no sim_status emitted.
    server.sim_connectors = []
    server._emit_sim_snapshot()
    assert not any(a_[0] == "sim_status" for a_, _k in server._emitted)


def test_forward_swallows_send_failure(server):
    """A connector that drops between is_connected() and send must not raise into
    the shot pipeline — the failure is logged + emitted as sim_send_failed instead
    (PR #115 review #1). send_raw raises ConnectionError on a raced disconnect, and
    the OSError guard catches it.
    """

    def _raise_disconnect(resolved):
        raise ConnectionError("send_raw called while not connected")

    boom = _FakeConnector("gspro", connected=True)
    boom.send_shot = _raise_disconnect
    other = _FakeConnector("opengolfsim", connected=True)
    server.sim_connectors = [boom, other]

    server._forward_shot_to_simulators(_shot())  # must not raise

    failed = [a_ for a_, k in server._emitted if a_[0] == "sim_send_failed"]
    assert len(failed) == 1 and failed[0][1]["target"] == "gspro"
    # a failed connector must not block delivery to the others
    assert len(other.sent) == 1
