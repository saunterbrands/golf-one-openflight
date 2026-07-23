#!/bin/bash
#
# Ordered graphical-session startup for the Golf One Raspberry Pi appliance.
#
# The session cover is established before the Raspberry Pi desktop starts.
# Chromium then opens a local Golf One loading page immediately while the
# backend initializes. The cover is dismissed only after the branded loading
# page reports painted frames, leaving Golf One—not the Pi desktop—underneath.
#

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
KIOSK_PROFILE_DIR="${GOLF_ONE_BROWSER_PROFILE_DIR:-$HOME/.config/golf-one-kiosk/chromium}"
KIOSK_URL="${GOLF_ONE_KIOSK_URL:-http://localhost:8080/}"
BOOT_PAGE="$PROJECT_DIR/scripts/setup/kiosk-loading.html"
BOOT_PAGE_URL="file://$BOOT_PAGE#$KIOSK_URL"
COVER_IMAGE="$PROJECT_DIR/scripts/setup/session-cover.png"
COVER_PID_FILE="$RUNTIME_DIR/golf-one-session-cover.pid"
COVER_READY_FILE="$RUNTIME_DIR/golf-one-session-cover.ready"
PAGE_READY_FILE="$RUNTIME_DIR/golf-one-loading-page.ready"
PAGE_REQUEST_FILE="$RUNTIME_DIR/golf-one-loading-page.request"
PAGE_READY_PORT=38917
SESSION_LOG="${GOLF_ONE_SESSION_LOG:-$HOME/golf-one-kiosk.log}"
COVER_PID=""
COVER_WATCHER_PID=""
PAGE_READY_SERVER_PID=""
BOOT_BROWSER_PID=""
APP_PID=""
SESSION_TERMINATING=0

mkdir -p "$RUNTIME_DIR"
exec >>"$SESSION_LOG" 2>&1

session_log() {
    printf '[Golf One session] %s %s\n' "$(date --iso-8601=seconds)" "$*"
}

stop_exact_pid() {
    local pid="${1:-}"

    case "$pid" in
        ''|*[!0-9]*) return 0 ;;
    esac

    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        for _ in $(seq 1 40); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.05
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -KILL "$pid" 2>/dev/null || true
        fi
    fi
}

clear_stale_session_cover() {
    local stale_pid=""

    if [ -r "$COVER_PID_FILE" ]; then
        stale_pid="$(sed -n '1p' "$COVER_PID_FILE")"
    fi
    case "$stale_pid" in
        ''|*[!0-9]*) ;;
        *)
            if [ "$(cat "/proc/$stale_pid/comm" 2>/dev/null || true)" = "swaylock" ]; then
                stop_exact_pid "$stale_pid"
            fi
            ;;
    esac
    rm -f -- "$COVER_PID_FILE" "$COVER_READY_FILE"
}

show_session_cover() {
    clear_stale_session_cover

    if [ ! -x /usr/bin/swaylock ]; then
        session_log "FATAL: swaylock is unavailable; refusing to expose the desktop"
        return 1
    fi
    if [ ! -f "$COVER_IMAGE" ]; then
        session_log "FATAL: session cover is missing: $COVER_IMAGE"
        return 1
    fi

    : >"$COVER_READY_FILE"
    /usr/bin/swaylock \
        --no-unlock-indicator \
        --image "$COVER_IMAGE" \
        --scaling fill \
        --ready-fd 3 \
        3>"$COVER_READY_FILE" &
    COVER_PID=$!
    printf '%s\n' "$COVER_PID" >"$COVER_PID_FILE"

    for _ in $(seq 1 80); do
        if [ -s "$COVER_READY_FILE" ] && kill -0 "$COVER_PID" 2>/dev/null; then
            session_log "Golf One cover ready (pid $COVER_PID)"
            rm -f -- "$COVER_READY_FILE"
            return 0
        fi
        if ! kill -0 "$COVER_PID" 2>/dev/null; then
            break
        fi
        sleep 0.05
    done

    session_log "FATAL: swaylock did not establish the Golf One cover"
    stop_exact_pid "$COVER_PID"
    COVER_PID=""
    rm -f -- "$COVER_PID_FILE" "$COVER_READY_FILE"
    return 1
}

find_profile_browser_pids() {
    local required_arg="${1:-}"
    local cmdline pid argv0 process_name

    for cmdline in /proc/[0-9]*/cmdline; do
        [ -r "$cmdline" ] || continue
        pid="${cmdline#/proc/}"
        pid="${pid%/cmdline}"
        argv0="$(tr '\0' '\n' <"$cmdline" 2>/dev/null | sed -n '1p')"
        process_name="${argv0##*/}"
        case "$process_name" in
            chromium*|chrome*) ;;
            *) continue ;;
        esac
        if ! tr '\0' '\n' <"$cmdline" 2>/dev/null \
            | grep -Fxq -- "--user-data-dir=$KIOSK_PROFILE_DIR"; then
            continue
        fi
        if [ -n "$required_arg" ] \
            && ! tr '\0' '\n' <"$cmdline" 2>/dev/null | grep -Fxq -- "$required_arg"; then
            continue
        fi
        printf '%s\n' "$pid"
    done
}

stop_stale_profile_browsers() {
    local pids pid

    pids="$(find_profile_browser_pids)"
    if [ -z "$pids" ]; then
        return 0
    fi

    session_log "Stopping stale Golf One Chromium profile before kiosk launch"
    while IFS= read -r pid; do
        stop_exact_pid "$pid"
    done <<EOF
$pids
EOF

    if [ -n "$(find_profile_browser_pids)" ]; then
        session_log "FATAL: stale Golf One Chromium processes did not stop"
        return 1
    fi
}

start_loading_page_ready_server() {
    rm -f -- "$PAGE_READY_FILE" "$PAGE_REQUEST_FILE"

    (
        while [ ! -s "$PAGE_READY_FILE" ]; do
            : >"$PAGE_REQUEST_FILE"
            if printf 'HTTP/1.1 204 No Content\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n' \
                | /usr/bin/nc -l -N 127.0.0.1 "$PAGE_READY_PORT" >"$PAGE_REQUEST_FILE" 2>/dev/null; then
                if grep -Eq '^GET /ready([?[:space:]])' "$PAGE_REQUEST_FILE"; then
                    printf 'ready\n' >"$PAGE_READY_FILE"
                    break
                fi
            else
                sleep 0.1
            fi
        done
    ) &
    PAGE_READY_SERVER_PID=$!
    session_log "Waiting for the Golf One loading page paint handshake"
}

start_raspberry_pi_desktop() {
    # Keep the familiar Pi desktop available behind the kiosk. It becomes
    # visible only after the protected 10-tap/PIN exit closes Chromium.
    /usr/bin/lwrespawn /usr/bin/pcmanfm-pi &
    /usr/bin/lwrespawn /usr/bin/wf-panel-pi &
    /usr/bin/lxsession-xdg-autostart &
    session_log "Raspberry Pi desktop started behind the Golf One cover"
}

dismiss_session_cover() {
    if [ -n "$COVER_PID" ] \
        && [ "$(cat "/proc/$COVER_PID/comm" 2>/dev/null || true)" = "swaylock" ]; then
        stop_exact_pid "$COVER_PID"
        session_log "Golf One cover dismissed after the loading page painted"
    fi
    COVER_PID=""
    rm -f -- "$COVER_PID_FILE"
}

wait_for_loading_page_ready() {
    for _ in $(seq 1 240); do
        if kill -0 "$BOOT_BROWSER_PID" 2>/dev/null \
            && [ -s "$PAGE_READY_FILE" ] \
            && [ -n "$(find_profile_browser_pids --type=renderer)" ]; then
            session_log "Golf One loading page reported its first painted frames"
            return 0
        fi
        if ! kill -0 "$BOOT_BROWSER_PID" 2>/dev/null; then
            session_log "FATAL: Chromium exited before the Golf One loading page painted"
            return 1
        fi
        sleep 0.25
    done

    session_log "FATAL: loading page did not paint within 60 seconds; Golf One cover remains active"
    return 1
}

cleanup_session() {
    local exit_status=$?

    trap - EXIT HUP INT TERM
    stop_exact_pid "$COVER_WATCHER_PID"
    stop_exact_pid "$PAGE_READY_SERVER_PID"
    stop_exact_pid "$APP_PID"
    if [ -n "$BOOT_BROWSER_PID" ] \
        && tr '\0' '\n' <"/proc/$BOOT_BROWSER_PID/cmdline" 2>/dev/null \
            | grep -Fxq -- "--user-data-dir=$KIOSK_PROFILE_DIR"; then
        stop_exact_pid "$BOOT_BROWSER_PID"
    fi
    if [ "$SESSION_TERMINATING" = "1" ]; then
        dismiss_session_cover
    fi
    rm -f -- "$COVER_READY_FILE" "$PAGE_READY_FILE" "$PAGE_REQUEST_FILE"
    exit "$exit_status"
}

terminate_session() {
    SESSION_TERMINATING=1
    exit 0
}

main() {
    session_log "Starting ordered Golf One appliance session"

    if ! wlr-randr --output DSI-2 --transform 90; then
        session_log "could not apply DSI-2 transform 90"
    fi

    if ! show_session_cover; then
        # Labwc's empty background remains in place. Do not start the Pi
        # desktop when the branded cover cannot be proven ready.
        while :; do sleep 3600; done
    fi

    if ! stop_stale_profile_browsers; then
        while :; do sleep 3600; done
    fi

    start_loading_page_ready_server
    "$SCRIPT_DIR/open-kiosk-browser.sh" "$BOOT_PAGE_URL" &
    BOOT_BROWSER_PID=$!
    wait_for_loading_page_ready &
    COVER_WATCHER_PID=$!

    GOLF_ONE_BROWSER_ALREADY_RUNNING=1 \
        GOLF_ONE_KIOSK_URL="$KIOSK_URL" \
        "$SCRIPT_DIR/launch-golf-one.sh" &
    APP_PID=$!
    if wait "$COVER_WATCHER_PID"; then
        # The desktop is needed only for the protected exit. Create it after
        # Chromium has painted, while swaylock still owns the visible frame.
        start_raspberry_pi_desktop
        sleep 0.75
        if kill -0 "$BOOT_BROWSER_PID" 2>/dev/null \
            && [ -s "$PAGE_READY_FILE" ]; then
            dismiss_session_cover
        else
            session_log "FATAL: browser readiness was lost; Golf One cover remains active"
        fi
    fi
    COVER_WATCHER_PID=""
    wait "$PAGE_READY_SERVER_PID" 2>/dev/null || true
    PAGE_READY_SERVER_PID=""
    rm -f -- "$PAGE_REQUEST_FILE"
    wait "$APP_PID"
    APP_PID=""

    # If a server survived a graphical-session restart, launch-golf-one
    # intentionally reuses it and returns immediately. Keep this session
    # wrapper alive until that server or the exact boot browser exits.
    while kill -0 "$BOOT_BROWSER_PID" 2>/dev/null \
        && curl -fsS --max-time 2 "$KIOSK_URL" >/dev/null 2>&1; do
        sleep 1
    done
}

trap cleanup_session EXIT
trap terminate_session HUP INT TERM

main "$@"
