"""Tests for the kiosk browser rendering-path configuration."""

from pathlib import Path


def test_kiosk_prefers_native_wayland_and_reduced_motion():
    script = (Path(__file__).resolve().parents[1] / "scripts/start-kiosk.sh").read_text(encoding="utf-8")

    assert 'RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"' in script
    assert 'for candidate in "$RUNTIME_DIR"/wayland-*' in script
    assert '[ -S "$RUNTIME_DIR/$WAYLAND_SOCKET" ]' in script
    assert "--ozone-platform=wayland" in script
    assert "--ozone-platform=x11" in script
    assert "--force-prefers-reduced-motion" in script
