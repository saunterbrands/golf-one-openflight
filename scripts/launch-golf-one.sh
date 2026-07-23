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

if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
    exec "$SCRIPT_DIR/open-kiosk-browser.sh" "$KIOSK_URL"
fi

if [ "$#" -gt 0 ]; then
    exec "$SCRIPT_DIR/start-kiosk.sh" "$@"
fi

exec "$SCRIPT_DIR/start-kiosk.sh" "${DEFAULT_ARGS[@]}"
