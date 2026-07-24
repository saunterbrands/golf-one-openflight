#!/bin/bash
#
# GNOME/X11 autostart entry point.
#
# GNOME can leave a newly autologged-in session in Activities Overview while
# applications started from ~/.config/autostart are already running. Open the
# branded Golf One loading page immediately, start the backend in the existing
# browser profile, then leave Overview and focus the exact kiosk window.
#
# Outside GNOME/X11, or without xdotool, this helper deliberately becomes the
# normal portable launcher so Wayland and appliance sessions are unchanged.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
KIOSK_URL="${GOLF_ONE_KIOSK_URL:-http://localhost:8080/}"
BOOT_PAGE="$PROJECT_DIR/scripts/setup/kiosk-loading.html"
BOOT_PAGE_URL="file://$BOOT_PAGE#$KIOSK_URL"
PAGE_READY_FILE="$RUNTIME_DIR/golf-one-gnome-loading-page.ready"
PAGE_REQUEST_FILE="$RUNTIME_DIR/golf-one-gnome-loading-page.request"
PAGE_READY_PORT=38917
WINDOW_CLASS="${GOLF_ONE_GNOME_WINDOW_CLASS:-GolfOneKiosk}"
FOCUS_ATTEMPTS="${GOLF_ONE_GNOME_FOCUS_ATTEMPTS:-240}"
FOCUS_DELAY="${GOLF_ONE_GNOME_FOCUS_DELAY:-0.25}"
MONITOR_DELAY="${GOLF_ONE_GNOME_MONITOR_DELAY:-0.5}"
LAUNCH_SCRIPT="${GOLF_ONE_LAUNCH_SCRIPT:-$SCRIPT_DIR/launch-golf-one.sh}"
BROWSER_SCRIPT="${GOLF_ONE_BROWSER_SCRIPT:-$SCRIPT_DIR/open-kiosk-browser.sh}"

PAGE_READY_SERVER_PID=""
BOOT_BROWSER_PID=""
FOCUS_PID=""
APP_PID=""

is_gnome_x11_session() {
    case "${XDG_CURRENT_DESKTOP:-}" in
        *GNOME*|*gnome*) ;;
        *) return 1 ;;
    esac
    [ "${XDG_SESSION_TYPE:-}" = "x11" ] || return 1
    [ -n "${DISPLAY:-}" ] || return 1
    command -v xdotool >/dev/null 2>&1
}

stop_child() {
    local pid="${1:-}"

    case "$pid" in
        ""|*[!0-9]*) return 0 ;;
    esac
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    fi
}

cleanup() {
    local exit_status=$?

    trap - EXIT HUP INT TERM
    stop_child "$PAGE_READY_SERVER_PID"
    stop_child "$FOCUS_PID"
    stop_child "$APP_PID"
    stop_child "$BOOT_BROWSER_PID"
    rm -f -- "$PAGE_READY_FILE" "$PAGE_REQUEST_FILE"
    exit "$exit_status"
}

start_loading_page_ready_server() {
    local netcat

    rm -f -- "$PAGE_READY_FILE" "$PAGE_REQUEST_FILE"
    netcat="$(command -v nc 2>/dev/null || true)"
    if [ -z "$netcat" ]; then
        echo "[Golf One GNOME] nc is unavailable; continuing without the paint handshake" >&2
        return 0
    fi

    (
        while [ ! -s "$PAGE_READY_FILE" ]; do
            : >"$PAGE_REQUEST_FILE"
            if printf 'HTTP/1.1 204 No Content\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n' \
                | "$netcat" -l -N 127.0.0.1 "$PAGE_READY_PORT" \
                    >"$PAGE_REQUEST_FILE" 2>/dev/null; then
                if grep -Eq '^GET /ready([?[:space:]])' "$PAGE_REQUEST_FILE"; then
                    printf 'ready\n' >"$PAGE_READY_FILE"
                    echo "[Golf One GNOME] Branded loading page painted"
                    break
                fi
            else
                sleep 0.1
            fi
        done
    ) &
    PAGE_READY_SERVER_PID=$!
}

focus_kiosk_window() {
    local attempt candidate window_id window_ids

    case "$FOCUS_ATTEMPTS" in
        ""|*[!0-9]*) FOCUS_ATTEMPTS=240 ;;
    esac

    for ((attempt = 0; attempt < FOCUS_ATTEMPTS; attempt++)); do
        window_ids="$(
            xdotool search --onlyvisible --class "$WINDOW_CLASS" 2>/dev/null || true
        )"
        window_id=""
        while IFS= read -r candidate; do
            case "$candidate" in
                ""|*[!0-9]*) ;;
                *)
                    window_id="$candidate"
                    break
                    ;;
            esac
        done <<<"$window_ids"

        if [ -n "$window_id" ]; then
            # Escape dismisses GNOME Activities Overview. Activating the
            # uniquely classed Chromium window then keeps keyboard/touch input
            # on the kiosk even if another login application mapped meanwhile.
            xdotool key --clearmodifiers Escape >/dev/null 2>&1 || true
            sleep 0.1
            xdotool windowactivate --sync "$window_id" >/dev/null 2>&1 || true
            xdotool windowraise "$window_id" >/dev/null 2>&1 || true
            xdotool windowfocus "$window_id" >/dev/null 2>&1 || true
            echo "[Golf One GNOME] Focused kiosk window $window_id"
            return 0
        fi
        sleep "$FOCUS_DELAY" 2>/dev/null || sleep 0.25
    done

    echo "[Golf One GNOME] Kiosk window did not appear before the focus timeout" >&2
    return 0
}

dashboard_is_healthy() {
    command -v curl >/dev/null 2>&1 \
        && curl -fsS --max-time 2 "$KIOSK_URL" >/dev/null 2>&1
}

main() {
    local app_status

    if ! is_gnome_x11_session; then
        exec "$LAUNCH_SCRIPT" "$@"
    fi

    mkdir -p "$RUNTIME_DIR"
    start_loading_page_ready_server
    "$BROWSER_SCRIPT" "$BOOT_PAGE_URL" &
    BOOT_BROWSER_PID=$!
    focus_kiosk_window &
    FOCUS_PID=$!

    GOLF_ONE_BROWSER_ALREADY_RUNNING=1 \
        GOLF_ONE_KIOSK_URL="$KIOSK_URL" \
        "$LAUNCH_SCRIPT" "$@" &
    APP_PID=$!

    wait "$APP_PID"
    app_status=$?
    APP_PID=""

    # launch-golf-one exits immediately when it finds a surviving healthy
    # server. In that recovery case, retain ownership of this browser until
    # either the user closes it or the server stops responding.
    if [ "$app_status" -eq 0 ]; then
        while kill -0 "$BOOT_BROWSER_PID" 2>/dev/null && dashboard_is_healthy; do
            sleep "$MONITOR_DELAY" 2>/dev/null || sleep 0.5
        done
    fi

    return "$app_status"
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

main "$@"
