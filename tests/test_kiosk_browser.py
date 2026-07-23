"""Tests for the kiosk browser rendering-path configuration."""

from pathlib import Path


def test_kiosk_prefers_native_wayland_and_reduced_motion():
    repo_root = Path(__file__).resolve().parents[1]
    start_script = (repo_root / "scripts/start-kiosk.sh").read_text(encoding="utf-8")
    browser_script = (repo_root / "scripts/open-kiosk-browser.sh").read_text(encoding="utf-8")

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


def test_desktop_recovery_launcher_reuses_live_server_or_starts_simulator():
    repo_root = Path(__file__).resolve().parents[1]
    launcher = (repo_root / "scripts/launch-golf-one.sh").read_text(encoding="utf-8")
    desktop = (repo_root / "scripts/setup/GolfOne.desktop").read_text(encoding="utf-8")

    assert 'HEALTH_URL="${GOLF_ONE_SERVER_HEALTH_URL:-http://localhost:8080}"' in launcher
    assert "curl -fsS" in launcher
    assert 'exec "$SCRIPT_DIR/open-kiosk-browser.sh" "$KIOSK_URL"' in launcher
    assert "http://localhost:8080/?autolaunch=1" in launcher
    assert "DEFAULT_ARGS=(--mock --sim)" in launcher
    assert "Name=Golf One Simulator" in desktop
    assert "/home/openflight/golf-one-openflight/scripts/launch-golf-one.sh" in desktop


def test_session_installer_preserves_rotation_and_installs_recovery_launcher():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "scripts/setup/install-golf-one-session.sh").read_text(
        encoding="utf-8"
    )
    autostart = (repo_root / "scripts/setup/labwc-autostart").read_text(encoding="utf-8")

    assert 'cp "$LABWC_DIR/autostart" "$BACKUP_DIR/labwc-autostart.$STAMP"' in installer
    assert 'install -m 0644 "$SCRIPT_DIR/labwc-autostart" "$LABWC_DIR/autostart"' in installer
    assert 'install -m 0755 "$SCRIPT_DIR/GolfOne.desktop"' in installer
    assert "wlr-randr --output DSI-2 --transform 90" in autostart
    assert "./scripts/launch-golf-one.sh --mock --sim" in autostart
