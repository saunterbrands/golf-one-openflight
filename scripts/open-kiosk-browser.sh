#!/bin/bash
#
# Open the Golf One dashboard in a persistent Chromium kiosk profile.
# This helper is shared by normal startup and the desktop recovery launcher.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
KIOSK_URL="${1:-http://localhost:8080/?autolaunch=1}"
PROFILE_DIR="${GOLF_ONE_BROWSER_PROFILE_DIR:-$HOME/.config/golf-one-kiosk/chromium}"
EXTENSION_DIR="${GOLF_ONE_BROWSER_EXTENSION_DIR:-$PROJECT_DIR/browser-extension}"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
WAYLAND_SOCKET="${WAYLAND_DISPLAY:-}"

if [ -z "$WAYLAND_SOCKET" ]; then
    for candidate in "$RUNTIME_DIR"/wayland-*; do
        if [ -S "$candidate" ]; then
            WAYLAND_SOCKET="${candidate##*/}"
            break
        fi
    done
fi
WAYLAND_SOCKET="${WAYLAND_SOCKET:-wayland-0}"

mkdir -p "$PROFILE_DIR"

CHROME_FLAGS=(
    --kiosk
    --noerrdialogs
    --disable-infobars
    --disable-session-crashed-bubble
    --no-first-run
    --password-store=basic
    --force-prefers-reduced-motion
    --enable-gpu-rasterization
    --use-angle=gles
    "--user-data-dir=$PROFILE_DIR"
)

if [ -f "$EXTENSION_DIR/manifest.json" ]; then
    CHROME_FLAGS+=(
        "--disable-extensions-except=$EXTENSION_DIR"
        "--load-extension=$EXTENSION_DIR"
    )
fi

if [ -S "$RUNTIME_DIR/$WAYLAND_SOCKET" ]; then
    export XDG_RUNTIME_DIR="$RUNTIME_DIR"
    export WAYLAND_DISPLAY="$WAYLAND_SOCKET"
    CHROME_FLAGS+=(--ozone-platform=wayland)
    echo "[Golf One] Using native Wayland kiosk rendering ($WAYLAND_DISPLAY)"
else
    CHROME_FLAGS+=(--ozone-platform=x11)
    echo "[Golf One] Wayland socket not found; using X11 kiosk rendering"
fi

if command -v chromium-browser &>/dev/null; then
    exec env DISPLAY=:0 chromium-browser "${CHROME_FLAGS[@]}" "$KIOSK_URL"
elif command -v chromium &>/dev/null; then
    exec env DISPLAY=:0 chromium "${CHROME_FLAGS[@]}" "$KIOSK_URL"
elif command -v google-chrome &>/dev/null; then
    exec env DISPLAY=:0 google-chrome "${CHROME_FLAGS[@]}" "$KIOSK_URL"
elif command -v firefox &>/dev/null; then
    exec env DISPLAY=:0 firefox --kiosk "$KIOSK_URL"
fi

echo "[Golf One] No supported kiosk browser found" >&2
exit 1
