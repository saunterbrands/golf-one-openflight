#!/bin/bash
#
# Ordered graphical-session startup for the Golf One Raspberry Pi appliance.
#
# A branded Wayland background is established before Chromium opens a local
# Golf One loading page. The Raspberry Pi desktop is not created during boot
# at all; it is created only after the app records the authenticated
# 10-tap/PIN exit. The background remains behind Chromium as fail-closed crash
# recovery without blocking the browser from painting.
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
PAGE_READY_FILE="$RUNTIME_DIR/golf-one-loading-page.ready"
PAGE_REQUEST_FILE="$RUNTIME_DIR/golf-one-loading-page.request"
DESKTOP_REQUEST_FILE="$RUNTIME_DIR/golf-one-desktop-exit.request"
PAGE_READY_PORT=38917
SESSION_LOG="${GOLF_ONE_SESSION_LOG:-$HOME/golf-one-kiosk.log}"
COVER_PID=""
COVER_PGID=""
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

process_is_live() {
    local pid="${1:-}"
    local state

    case "$pid" in
        ''|*[!0-9]*) return 1 ;;
    esac

    state="$(ps -o stat= -p "$pid" 2>/dev/null | tr -d ' ' || true)"
    [ -n "$state" ] && [ "${state#Z}" = "$state" ]
}

stop_process_tree() {
    local parent_pid="${1:-}"
    local child_pid

    case "$parent_pid" in
        ''|*[!0-9]*) return 0 ;;
    esac

    for child_pid in $(pgrep -P "$parent_pid" 2>/dev/null || true); do
        stop_process_tree "$child_pid"
    done
    stop_exact_pid "$parent_pid"
}

process_group_exists() {
    local pgid="${1:-}"

    case "$pgid" in
        ''|*[!0-9]*) return 1 ;;
    esac
    ps -eo pgid=,stat= \
        | awk -v expected="$pgid" '$1 == expected && $2 !~ /^Z/ { found = 1 } END { exit !found }'
}

stop_process_group() {
    local pgid="${1:-}"
    local own_pgid

    case "$pgid" in
        ''|*[!0-9]*) return 0 ;;
    esac
    own_pgid="$(ps -o pgid= -p "$$" | tr -d ' ')"
    if [ "$pgid" = "$own_pgid" ]; then
        session_log "FATAL: refusing to stop the appliance session process group"
        return 1
    fi

    if process_group_exists "$pgid"; then
        kill -TERM -- "-$pgid" 2>/dev/null || true
        for _ in $(seq 1 40); do
            process_group_exists "$pgid" || break
            sleep 0.05
        done
        if process_group_exists "$pgid"; then
            kill -KILL -- "-$pgid" 2>/dev/null || true
        fi
    fi
}

clear_stale_session_cover() {
    local stale_pid=""
    local stale_pgid=""

    if [ -r "$COVER_PID_FILE" ]; then
        read -r stale_pid stale_pgid <"$COVER_PID_FILE" || true
    fi
    case "$stale_pid" in
        ''|*[!0-9]*) ;;
        *)
            case "$(cat "/proc/$stale_pid/comm" 2>/dev/null || true)" in
                swaybg|swaylock)
                if [ -n "$stale_pgid" ] \
                    && [ "$(ps -o pgid= -p "$stale_pid" | tr -d ' ')" = "$stale_pgid" ]; then
                    stop_process_group "$stale_pgid"
                else
                    # Compatibility with the first installer revision, which
                    # recorded only the cover's parent PID.
                    stop_process_tree "$stale_pid"
                fi
                ;;
            esac
            ;;
    esac
    rm -f -- "$COVER_PID_FILE"
}

show_session_cover() {
    local candidate_pgid=""

    clear_stale_session_cover

    if [ ! -x /usr/bin/swaybg ]; then
        session_log "FATAL: swaybg is unavailable; refusing to start the kiosk"
        return 1
    fi
    if [ ! -f "$COVER_IMAGE" ]; then
        session_log "FATAL: session cover is missing: $COVER_IMAGE"
        return 1
    fi

    /usr/bin/setsid /usr/bin/swaybg \
        --output DSI-2 \
        --image "$COVER_IMAGE" \
        --mode fill \
        --color 173a30 &
    COVER_PID=$!
    COVER_PGID=""
    for _ in $(seq 1 40); do
        candidate_pgid="$(ps -o pgid= -p "$COVER_PID" | tr -d ' ')"
        if [ "$candidate_pgid" = "$COVER_PID" ]; then
            COVER_PGID="$candidate_pgid"
            break
        fi
        kill -0 "$COVER_PID" 2>/dev/null || break
        sleep 0.025
    done
    if [ -z "$COVER_PGID" ] || [ "$COVER_PGID" != "$COVER_PID" ]; then
        session_log "FATAL: swaybg did not enter an isolated process group"
        stop_process_tree "$COVER_PID"
        COVER_PID=""
        COVER_PGID=""
        return 1
    fi
    printf '%s %s\n' "$COVER_PID" "$COVER_PGID" >"$COVER_PID_FILE"

    for _ in $(seq 1 40); do
        if process_is_live "$COVER_PID"; then
            # swaybg connects, creates its layer surface, and commits it before
            # entering the event loop represented by this stable live process.
            sleep 0.1
            if process_is_live "$COVER_PID"; then
                session_log "Golf One background ready (pid $COVER_PID, pgid $COVER_PGID)"
                return 0
            fi
        fi
        if ! kill -0 "$COVER_PID" 2>/dev/null; then
            break
        fi
        sleep 0.05
    done

    session_log "FATAL: swaybg did not establish the Golf One background"
    stop_process_group "$COVER_PGID"
    COVER_PID=""
    COVER_PGID=""
    rm -f -- "$COVER_PID_FILE"
    return 1
}

find_profile_browser_pids() {
    local required_arg="${1:-}"
    local cmdline pid cmdline_text argv0 process_name

    for cmdline in /proc/[0-9]*/cmdline; do
        [ -r "$cmdline" ] || continue
        pid="${cmdline#/proc/}"
        pid="${pid%/cmdline}"
        # Chromium rewrites /proc/PID/cmdline into a single space-delimited
        # process title on Raspberry Pi OS. Normal processes retain NULs.
        # Normalize both representations, then require whole argument tokens.
        cmdline_text="$(tr '\0' ' ' <"$cmdline" 2>/dev/null)"
        argv0="${cmdline_text%% *}"
        process_name="${argv0##*/}"
        case "$process_name" in
            chromium*|chrome*) ;;
            *) continue ;;
        esac
        case " $cmdline_text " in
            *" --user-data-dir=$KIOSK_PROFILE_DIR "*) ;;
            *) continue ;;
        esac
        if [ -n "$required_arg" ]; then
            case " $cmdline_text " in
                *" $required_arg "*) ;;
                *) continue ;;
            esac
        fi
        printf '%s\n' "$pid"
    done
}

browser_pid_uses_profile() {
    local pid="${1:-}"
    local cmdline_text

    case "$pid" in
        ''|*[!0-9]*) return 1 ;;
    esac
    [ -r "/proc/$pid/cmdline" ] || return 1
    cmdline_text="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null)"
    case " $cmdline_text " in
        *" --user-data-dir=$KIOSK_PROFILE_DIR "*) return 0 ;;
        *) return 1 ;;
    esac
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
    # Create the Pi desktop only after the protected 10-tap/PIN exit closes
    # Chromium. It is never part of the boot-time surface stack.
    /usr/bin/lwrespawn /usr/bin/pcmanfm-pi &
    /usr/bin/lwrespawn /usr/bin/wf-panel-pi &
    /usr/bin/lxsession-xdg-autostart &
    session_log "Raspberry Pi desktop started after authenticated Golf One exit"
}

desktop_exit_is_valid() {
    local marker_mode marker_owner

    [ -f "$DESKTOP_REQUEST_FILE" ] || return 1
    [ ! -L "$DESKTOP_REQUEST_FILE" ] || return 1
    [ "$(cat "$DESKTOP_REQUEST_FILE" 2>/dev/null)" = "requested" ] || return 1
    marker_mode="$(stat -c '%a' "$DESKTOP_REQUEST_FILE" 2>/dev/null || true)"
    marker_owner="$(stat -c '%u' "$DESKTOP_REQUEST_FILE" 2>/dev/null || true)"
    [ "$marker_mode" = "600" ] || return 1
    [ "$marker_owner" = "$(id -u)" ] || return 1
}

dismiss_session_cover() {
    if [ -n "$COVER_PGID" ] && process_group_exists "$COVER_PGID"; then
        stop_process_group "$COVER_PGID"
        wait "$COVER_PID" 2>/dev/null || true
        session_log "Golf One background dismissed for Raspberry Pi desktop"
    fi
    COVER_PID=""
    COVER_PGID=""
    rm -f -- "$COVER_PID_FILE"
}

wait_for_browser_renderer() {
    for _ in $(seq 1 240); do
        if kill -0 "$BOOT_BROWSER_PID" 2>/dev/null \
            && [ -n "$(find_profile_browser_pids --type=renderer)" ]; then
            session_log "Chromium renderer ready behind the Golf One cover"
            return 0
        fi
        if ! kill -0 "$BOOT_BROWSER_PID" 2>/dev/null; then
            session_log "FATAL: Chromium exited before creating a renderer"
            return 1
        fi
        sleep 0.25
    done

    session_log "FATAL: Chromium renderer was not ready within 60 seconds"
    return 1
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

    session_log "FATAL: loading page did not paint within 60 seconds"
    return 1
}

wait_for_owned_app() {
    while process_is_live "$APP_PID"; do
        if ! browser_pid_uses_profile "$BOOT_BROWSER_PID"; then
            if ! desktop_exit_is_valid; then
                session_log "FATAL: Chromium exited without an authenticated desktop exit request"
                show_session_cover || true
                stop_exact_pid "$APP_PID"
            fi
            break
        fi
        sleep 0.25
    done

    wait "$APP_PID" 2>/dev/null || true
    APP_PID=""
}

cleanup_session() {
    local exit_status=$?

    trap - EXIT HUP INT TERM
    stop_exact_pid "$PAGE_READY_SERVER_PID"
    stop_exact_pid "$APP_PID"
    if browser_pid_uses_profile "$BOOT_BROWSER_PID"; then
        stop_exact_pid "$BOOT_BROWSER_PID"
    fi
    if [ "$SESSION_TERMINATING" = "1" ]; then
        dismiss_session_cover
    fi
    rm -f -- \
        "$PAGE_READY_FILE" \
        "$PAGE_REQUEST_FILE" \
        "$DESKTOP_REQUEST_FILE"
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
        # Labwc's empty background remains in place. Do not start Chromium or
        # the Pi desktop when the branded background cannot be proven alive.
        while :; do sleep 3600; done
    fi

    if ! stop_stale_profile_browsers; then
        while :; do sleep 3600; done
    fi

    rm -f -- "$DESKTOP_REQUEST_FILE"

    start_loading_page_ready_server
    "$SCRIPT_DIR/open-kiosk-browser.sh" "$BOOT_PAGE_URL" &
    BOOT_BROWSER_PID=$!

    GOLF_ONE_BROWSER_ALREADY_RUNNING=1 \
        GOLF_ONE_DESKTOP_EXIT_FILE="$DESKTOP_REQUEST_FILE" \
        GOLF_ONE_KIOSK_URL="$KIOSK_URL" \
        "$SCRIPT_DIR/launch-golf-one.sh" &
    APP_PID=$!

    # The branded layer-shell background remains behind Chromium. Unlike a
    # session lock, it permits Chromium to map and prove two painted frames
    # before the backend handoff.
    if ! wait_for_browser_renderer; then
        while :; do sleep 3600; done
    fi

    if ! wait_for_loading_page_ready; then
        stop_process_tree "$PAGE_READY_SERVER_PID"
        PAGE_READY_SERVER_PID=""
        while :; do sleep 3600; done
    fi
    wait "$PAGE_READY_SERVER_PID" 2>/dev/null || true
    PAGE_READY_SERVER_PID=""
    rm -f -- "$PAGE_REQUEST_FILE"
    wait_for_owned_app

    # If a server survived a graphical-session restart, launch-golf-one
    # intentionally reuses it and returns immediately. Keep the appliance
    # wrapper alive until that server or the exact boot browser exits.
    while kill -0 "$BOOT_BROWSER_PID" 2>/dev/null \
        && curl -fsS --max-time 2 "$KIOSK_URL" >/dev/null 2>&1; do
        sleep 1
    done

    if desktop_exit_is_valid; then
        rm -f -- "$DESKTOP_REQUEST_FILE"
        session_log "Authenticated Golf One exit received; starting Raspberry Pi desktop"
        start_raspberry_pi_desktop
        dismiss_session_cover
        return 0
    fi

    # A server crash or unverified Chromium close must never expose the Pi
    # desktop. Re-establish the branded cover and leave SSH as the recovery
    # path until the graphical session is deliberately restarted.
    session_log "FATAL: Golf One stopped without an authenticated desktop exit request"
    if [ -z "$COVER_PGID" ] || ! process_group_exists "$COVER_PGID"; then
        show_session_cover || true
    fi
    while :; do sleep 3600; done
}

trap cleanup_session EXIT
trap terminate_session HUP INT TERM

main "$@"
