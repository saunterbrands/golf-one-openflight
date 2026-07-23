"""Tests for the kiosk browser rendering-path configuration."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path


def _apply_calibration(matrix, point):
    """Apply a six-value libinput calibration matrix to a normalized point."""
    a, b, c, d, e, f = matrix
    x, y = point
    return (a * x + b * y + c, d * x + e * y + f)


def _rotate_counterclockwise(point):
    """Model the quarter-turn mismatch reported on the installed display."""
    x, y = point
    return (y, 1 - x)


def test_kiosk_prefers_native_wayland_and_reduced_motion():
    repo_root = Path(__file__).resolve().parents[1]
    start_script = (repo_root / "scripts/start-kiosk.sh").read_text(encoding="utf-8")
    browser_script = (repo_root / "scripts/open-kiosk-browser.sh").read_text(encoding="utf-8")

    assert 'export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"' in start_script
    assert '"$SCRIPT_DIR/open-kiosk-browser.sh" "$KIOSK_URL" &' in start_script
    assert 'RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"' in browser_script
    assert 'for candidate in "$RUNTIME_DIR"/wayland-*' in browser_script
    assert '[ -S "$RUNTIME_DIR/$WAYLAND_SOCKET" ]' in browser_script
    assert "--ozone-platform=wayland" in browser_script
    assert "--ozone-platform=x11" in browser_script
    assert "--force-prefers-reduced-motion" in browser_script
    assert "--password-store=basic" in browser_script
    assert "--user-data-dir=" in browser_script
    assert "http://localhost:8080/?autolaunch=1" in browser_script
    assert "--disable-extensions-except=" in browser_script
    assert "--load-extension=" in browser_script


def test_kiosk_fingerprints_extension_source_to_avoid_stale_service_workers():
    repo_root = Path(__file__).resolve().parents[1]
    browser_script = (repo_root / "scripts/open-kiosk-browser.sh").read_text(
        encoding="utf-8"
    )

    assert "EXTENSION_FINGERPRINT" in browser_script
    assert "EXTENSION_RUNTIME_DIR" in browser_script
    assert 'sha256sum "$EXTENSION_DIR/manifest.json"' in browser_script
    assert '"--load-extension=$EXTENSION_RUNTIME_DIR"' in browser_script


def test_desktop_recovery_launcher_reuses_live_server_or_starts_simulator():
    repo_root = Path(__file__).resolve().parents[1]
    launcher = (repo_root / "scripts/launch-golf-one.sh").read_text(encoding="utf-8")
    desktop = (repo_root / "scripts/setup/GolfOne.desktop").read_text(encoding="utf-8")

    assert 'HEALTH_URL="${GOLF_ONE_SERVER_HEALTH_URL:-http://localhost:8080}"' in launcher
    assert "curl -fsS" in launcher
    assert 'exec "$SCRIPT_DIR/open-kiosk-browser.sh" "$KIOSK_URL"' in launcher
    assert "http://localhost:8080/?autolaunch=1" in launcher
    assert "DEFAULT_ARGS=(--mock --sim)" in launcher
    assert "udevadm info -q property" in launcher
    assert "ID_VENDOR_ID=0483" in launcher
    assert "ID_VENDOR_ID=058b" in launcher
    assert "ID_MODEL_ID=0058" in launcher
    assert "GOLF_ONE_RADAR_PORT" in launcher
    assert 'compgen -G "/dev/ttyACM*"' not in launcher
    assert "DEFAULT_ARGS=(--sim)" in launcher
    assert "flock -n 9" in launcher
    assert "Name=Golf One" in desktop
    assert "/home/openflight/golf-one-openflight/scripts/launch-golf-one.sh" in desktop
    assert "--mock" not in desktop


def test_session_installer_preserves_rotation_and_installs_recovery_launcher():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "scripts/setup/install-golf-one-session.sh").read_text(
        encoding="utf-8"
    )
    autostart = (repo_root / "scripts/setup/labwc-autostart").read_text(encoding="utf-8")

    assert 'cp "$LABWC_DIR/autostart" "$BACKUP_DIR/labwc-autostart.$STAMP"' in installer
    assert 'cp "$LABWC_DIR/rc.xml" "$BACKUP_DIR/labwc-rc.$STAMP.xml"' in installer
    assert 'install -m 0644 "$SCRIPT_DIR/labwc-autostart" "$LABWC_DIR/autostart"' in installer
    assert 'install -m 0644 "$SCRIPT_DIR/labwc-rc.xml" "$LABWC_DIR/rc.xml"' in installer
    assert 'install -m 0755 "$SCRIPT_DIR/GolfOne.desktop"' in installer
    assert "wlr-randr --output DSI-2 --transform 90" in autostart
    assert "./scripts/launch-golf-one.sh" in autostart
    assert "--mock --sim" not in autostart


def test_waveshare_touch_calibration_cancels_reported_corner_rotation():
    repo_root = Path(__file__).resolve().parents[1]
    config_path = repo_root / "scripts/setup/labwc-rc.xml"
    root = ET.parse(config_path).getroot()
    namespace = {"labwc": "http://openbox.org/3.4/rc"}
    calibration = root.find(
        "./labwc:libinput/labwc:device"
        "[@category='Goodix Capacitive TouchScreen']/"
        "labwc:calibrationMatrix",
        namespace,
    )
    touch = root.find(
        "./labwc:touch[@deviceName='Goodix Capacitive TouchScreen']",
        namespace,
    )

    assert touch is None
    assert calibration is not None
    matrix = tuple(float(value) for value in calibration.text.split())
    assert matrix == (0, -1, 1, 1, 0, 0)

    corners = {
        "top-left": (0, 0),
        "bottom-left": (0, 1),
        "bottom-right": (1, 1),
        "top-right": (1, 0),
    }
    observed_before = {name: _rotate_counterclockwise(point) for name, point in corners.items()}
    observed_after = {
        name: _rotate_counterclockwise(_apply_calibration(matrix, point))
        for name, point in corners.items()
    }

    assert observed_before == {
        "top-left": (0, 1),
        "bottom-left": (1, 1),
        "bottom-right": (1, 0),
        "top-right": (0, 0),
    }
    assert observed_after == corners


def test_simulator_extension_exposes_persistent_display_settings():
    repo_root = Path(__file__).resolve().parents[1]
    content = (repo_root / "browser-extension/content.js").read_text(encoding="utf-8")
    background = (repo_root / "browser-extension/background.js").read_text(encoding="utf-8")

    assert "Display settings" in content
    assert "Golf One Settings" in content
    assert "golf-one-settings" in content
    assert "http://127.0.0.1:8080/?settings=1" in content
    assert "golf-one-status" in background


def test_simulator_extension_relays_local_shots_into_the_fuse_game():
    repo_root = Path(__file__).resolve().parents[1]
    content = (repo_root / "browser-extension/content.js").read_text(encoding="utf-8")
    background = (repo_root / "browser-extension/background.js").read_text(encoding="utf-8")

    assert 'iframe[title="fuse"]' in content
    assert "event.source !== gameFrame.contentWindow" in content
    assert "golf-one-game-session" in content
    assert "golf-one-game-poll" in content
    assert "golf-one-game-ack" in content
    assert "gameFrame.contentWindow.postMessage" in content
    assert "new URL(gameFrame.src).origin" in content
    assert "event.data.type === 'player'" in content
    assert "event.data.type === 'result'" in content
    assert "METERS_TO_YARDS = 1.0936133" in content
    assert "carryMeters * METERS_TO_YARDS" in content
    assert "/api/opengolfsim/browser/session" in background
    assert "/api/opengolfsim/browser/poll" in background
    assert "/api/opengolfsim/browser/ack" in background
    assert "'X-Golf-One-Extension': 'browser-relay-v1'" in background
    assert "sender?.origin" in background


def test_simulator_extension_manifest_rolls_out_browser_relay_worker():
    repo_root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (repo_root / "browser-extension/manifest.json").read_text(encoding="utf-8")
    )

    version = tuple(int(part) for part in manifest["version"].split("."))
    assert version >= (1, 2, 0)
    matches = manifest["content_scripts"][0]["matches"]
    assert "http://127.0.0.1:8080/offline-simulator*" in matches
    assert "http://localhost:8080/offline-simulator*" in matches


def test_simulator_extension_accepts_only_official_or_loopback_game_pages():
    repo_root = Path(__file__).resolve().parents[1]
    background = (repo_root / "browser-extension/background.js").read_text(
        encoding="utf-8"
    )

    assert "isSimulatorSender" in background
    assert "https://app.opengolfsim.com" in background
    assert "http://127.0.0.1:8080" in background
    assert "http://localhost:8080" in background


def test_simulator_extension_defaults_to_full_width_with_recoverable_controls():
    repo_root = Path(__file__).resolve().parents[1]
    content = (repo_root / "browser-extension/content.js").read_text(encoding="utf-8")

    assert "OpenGolfSim controls" in content
    assert "setProperty('margin-left', '0px', 'important')" in content
    assert "restoreOpenGolfSimLayout" in content


def test_simulator_extension_closes_stale_spa_games_and_recovers_visual_test():
    repo_root = Path(__file__).resolve().parents[1]
    content = (repo_root / "browser-extension/content.js").read_text(encoding="utf-8")

    assert "if (gameFrame && !nextFrame)" in content
    assert "closeGameSession('iframe-removed')" in content
    assert "DIRECT_RANGE_RECOVERY_MS" in content
    assert "inFlightShot = null" in content
    assert "window.location.pathname.startsWith('/fuse/examples/range')" in content
    assert "scheduleGameSessionRetry" in content
    assert "GAME_SESSION_RETRY_MAX_MS" in content


def test_offline_fuse_installer_is_pinned_and_keeps_third_party_code_out_of_repo():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (
        repo_root / "scripts/setup/install-offline-fuse-range.sh"
    ).read_text(encoding="utf-8")

    assert "6f10092c4444a538dd869d495eb2cb45697a5fb5" in installer
    assert "https://github.com/OpenGolfSim/fuse.git" in installer
    assert "GOLF_ONE_OFFLINE_FUSE_INSTALL_ROOT" in installer
    assert "LICENSE.md" in installer
    assert "password" not in installer.lower()
