#!/bin/bash
#
# Open the Golf One dashboard in a persistent Chromium kiosk profile.
# This helper is shared by normal startup and the desktop recovery launcher.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
KIOSK_URL="${1:-http://localhost:8080/}"
PROFILE_DIR="${GOLF_ONE_BROWSER_PROFILE_DIR:-$HOME/.config/golf-one-kiosk/chromium}"
SESSION_BACKUP_ROOT="${GOLF_ONE_BROWSER_SESSION_BACKUP_DIR:-$HOME/.cache/golf-one-kiosk/session-backups}"
EXTENSION_DIR="${GOLF_ONE_BROWSER_EXTENSION_DIR:-$PROJECT_DIR/browser-extension}"
EXTENSION_CACHE_ROOT="${GOLF_ONE_BROWSER_EXTENSION_CACHE_DIR:-$HOME/.cache/golf-one-kiosk/extensions}"
EXTENSION_RUNTIME_DIR="$EXTENSION_DIR"
PROC_ROOT="${GOLF_ONE_BROWSER_PROC_ROOT:-/proc}"
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

chromium_profile_is_live() {
    local lock_path="$PROFILE_DIR/SingletonLock"
    local lock_target lock_host lock_pid process_uid executable browser_name
    local argument profile_argument_found=0

    [ -L "$lock_path" ] || return 1
    lock_target="$(readlink "$lock_path" 2>/dev/null)" || return 1
    lock_pid="${lock_target##*-}"
    lock_host="${lock_target%-*}"

    case "$lock_pid" in
        ""|*[!0-9]*) return 1 ;;
    esac
    [ "$lock_host" = "$(hostname)" ] || return 1
    [ -r "$PROC_ROOT/$lock_pid/status" ] || return 1
    [ -r "$PROC_ROOT/$lock_pid/cmdline" ] || return 1

    process_uid="$(
        awk '$1 == "Uid:" { print $2; exit }' "$PROC_ROOT/$lock_pid/status"
    )"
    [ -n "$process_uid" ] || return 1
    [ "$process_uid" = "$(id -u)" ] || return 1

    executable="$(readlink "$PROC_ROOT/$lock_pid/exe" 2>/dev/null)" || return 1
    executable="${executable% (deleted)}"
    browser_name="${executable##*/}"
    case "$browser_name" in
        chromium|chromium-browser|chrome|google-chrome|google-chrome-stable) ;;
        *) return 1 ;;
    esac

    while IFS= read -r -d '' argument; do
        if [ "$argument" = "--user-data-dir=$PROFILE_DIR" ]; then
            profile_argument_found=1
            break
        fi
    done <"$PROC_ROOT/$lock_pid/cmdline"

    [ "$profile_argument_found" = "1" ]
}

rotate_session_restore_state() {
    local default_profile="$PROFILE_DIR/Default"
    local sessions_dir="$default_profile/Sessions"
    local backup_dir=""
    local state_path relative_path destination

    # A recovery launcher can be clicked while the existing kiosk is still
    # alive. In that case Chromium will handle the requested URL through its
    # ProcessSingleton; never move session files that process still owns.
    # A stale or malformed lock does not suppress normal session rotation.
    if chromium_profile_is_live; then
        echo "[Golf One] Chromium profile is already live; preserving active session files"
        return 0
    fi

    # Chromium's tab/session files are independent of cookies, saved
    # passwords, preferences, and extension storage. Move only the restore
    # files out of the live profile so a prior OpenGolfSim tab cannot take
    # precedence over the explicitly requested kiosk URL.
    for state_path in \
        "$default_profile/Current Session" \
        "$default_profile/Current Tabs" \
        "$default_profile/Last Session" \
        "$default_profile/Last Tabs" \
        "$sessions_dir"/Session_* \
        "$sessions_dir"/Tabs_*; do
        [ -f "$state_path" ] || continue

        if [ -z "$backup_dir" ]; then
            mkdir -p "$SESSION_BACKUP_ROOT"
            backup_dir="$(
                mktemp -d \
                    "$SESSION_BACKUP_ROOT/launch-$(date +%Y%m%d-%H%M%S)-XXXXXX"
            )"
            mkdir -p "$backup_dir/Default/Sessions"
        fi

        case "$state_path" in
            "$sessions_dir"/*)
                relative_path="Default/Sessions/${state_path##*/}"
                ;;
            *)
                relative_path="Default/${state_path##*/}"
                ;;
        esac
        destination="$backup_dir/$relative_path"
        mv "$state_path" "$destination"
    done

    if [ -n "$backup_dir" ]; then
        echo "[Golf One] Archived stale Chromium tab restore state to $backup_dir"
    fi
}

mkdir -p "$PROFILE_DIR"
rotate_session_restore_state

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
    # Chromium can retain an old Manifest V3 service worker in a persistent
    # profile even after an unpacked extension changes on disk. Loading each
    # source fingerprint from its own immutable path guarantees that the
    # background worker and content script come from the same build.
    if command -v sha256sum &>/dev/null; then
        EXTENSION_FINGERPRINT="$(
            sha256sum "$EXTENSION_DIR/manifest.json" "$EXTENSION_DIR/background.js" "$EXTENSION_DIR/content.js" \
                | sha256sum \
                | awk '{print $1}'
        )"
    else
        EXTENSION_FINGERPRINT="$(
            cksum "$EXTENSION_DIR/manifest.json" "$EXTENSION_DIR/background.js" "$EXTENSION_DIR/content.js" \
                | cksum \
                | awk '{print $1}'
        )"
    fi
    EXTENSION_RUNTIME_DIR="$EXTENSION_CACHE_ROOT/$EXTENSION_FINGERPRINT"
    if [ ! -f "$EXTENSION_RUNTIME_DIR/manifest.json" ]; then
        mkdir -p "$EXTENSION_RUNTIME_DIR"
        cp -R "$EXTENSION_DIR/." "$EXTENSION_RUNTIME_DIR/"
    fi

    CHROME_FLAGS+=(
        "--disable-extensions-except=$EXTENSION_RUNTIME_DIR"
        "--load-extension=$EXTENSION_RUNTIME_DIR"
    )
    echo "[Golf One] Loading extension build ${EXTENSION_FINGERPRINT:0:12}"
fi

if [ -S "$RUNTIME_DIR/$WAYLAND_SOCKET" ]; then
    export XDG_RUNTIME_DIR="$RUNTIME_DIR"
    export WAYLAND_DISPLAY="$WAYLAND_SOCKET"
    CHROME_FLAGS+=(--ozone-platform=wayland)
    echo "[Golf One] Using native Wayland kiosk rendering ($WAYLAND_DISPLAY)"
else
    CHROME_FLAGS+=(--ozone-platform=x11 --class=GolfOneKiosk)
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
