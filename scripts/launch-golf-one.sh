#!/bin/bash
#
# Desktop/autostart recovery entry point.
# Reopens the kiosk when the server is still healthy; otherwise starts the
# complete Golf One simulator stack.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEALTH_URL="${GOLF_ONE_SERVER_HEALTH_URL:-http://localhost:8080}"
KIOSK_URL="${GOLF_ONE_KIOSK_URL:-http://localhost:8080/?autolaunch=1}"
DEFAULT_ARGS=(--mock --sim)
LAUNCH_LOCK="${GOLF_ONE_LAUNCH_LOCK_FILE:-${XDG_RUNTIME_DIR:-/tmp}/golf-one-kiosk-launch.lock}"

# Use real launch-monitor hardware automatically when the OPS243-A is present.
# Do not treat every USB serial adapter as the radar: K-LD7 adapters and setup
# cables can also appear as ttyUSB/ttyACM devices.
ops243_is_present() {
    if [ -e /dev/ops243 ]; then
        return 0
    fi
    if [ -n "${GOLF_ONE_RADAR_PORT:-}" ] && [ -e "$GOLF_ONE_RADAR_PORT" ]; then
        return 0
    fi
    if ! command -v udevadm >/dev/null 2>&1; then
        return 1
    fi

    local device properties
    for device in /dev/ttyACM* /dev/ttyUSB*; do
        [ -e "$device" ] || continue
        properties="$(udevadm info -q property -n "$device" 2>/dev/null || true)"
        if printf '%s\n' "$properties" | grep -Eiq \
            '(^ID_VENDOR_ID=0483$|OmniPreSense|OPS243)'; then
            return 0
        fi
    done
    return 1
}

# Without a positively identified OPS243-A, keep the appliance usable in mock
# mode for setup and demos.
if ops243_is_present; then
    DEFAULT_ARGS=(--sim)
fi

if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
    exec "$SCRIPT_DIR/open-kiosk-browser.sh" "$KIOSK_URL"
fi

# Serialize the unhealthy-server startup window. This prevents Labwc and a
# desktop launch from racing two servers onto port 8080 during login.
if command -v flock >/dev/null 2>&1; then
    exec 9>"$LAUNCH_LOCK"
    if ! flock -n 9; then
        for _ in $(seq 1 60); do
            if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
                exec "$SCRIPT_DIR/open-kiosk-browser.sh" "$KIOSK_URL"
            fi
            sleep 0.5
        done
        if ! flock -n 9; then
            echo "[Golf One] Another kiosk launch is still in progress." >&2
            exit 1
        fi
    fi
fi

# The server may have become healthy while this process waited for the lock.
if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
    exec "$SCRIPT_DIR/open-kiosk-browser.sh" "$KIOSK_URL"
fi

if [ "$#" -gt 0 ]; then
    exec "$SCRIPT_DIR/start-kiosk.sh" "$@"
fi

exec "$SCRIPT_DIR/start-kiosk.sh" "${DEFAULT_ARGS[@]}"
