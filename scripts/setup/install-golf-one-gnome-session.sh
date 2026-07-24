#!/bin/bash
#
# Install the unprivileged GNOME/X11 autostart and recovery launchers.
# This intentionally does not alter GDM, the active desktop, display rotation,
# touch calibration, or any system-wide configuration.

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"
APPLICATIONS_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="${GOLF_ONE_DESKTOP_DIR:-$HOME/Desktop}"
BACKUP_ROOT="$HOME/.config/golf-one/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
AUTOSTART_TEMP="$(mktemp)"
DESKTOP_TEMP="$(mktemp)"
PROJECT_DIR_SED="$(printf '%s\n' "$PROJECT_DIR" | sed 's/[&|]/\\&/g')"
BACKUP_DIR=""

cleanup() {
    rm -f -- "$AUTOSTART_TEMP" "$DESKTOP_TEMP"
}
trap cleanup EXIT HUP INT TERM

sed "s|@GOLF_ONE_PROJECT_DIR@|$PROJECT_DIR_SED|g" \
    "$SCRIPT_DIR/GolfOneGnomeAutostart.desktop" >"$AUTOSTART_TEMP"
sed "s|@GOLF_ONE_PROJECT_DIR@|$PROJECT_DIR_SED|g" \
    "$SCRIPT_DIR/GolfOne.desktop" >"$DESKTOP_TEMP"
if grep -q '@GOLF_ONE_PROJECT_DIR@' "$AUTOSTART_TEMP" "$DESKTOP_TEMP"; then
    echo "Could not render the Golf One GNOME session files." >&2
    exit 1
fi

mkdir -p \
    "$AUTOSTART_DIR" \
    "$APPLICATIONS_DIR" \
    "$DESKTOP_DIR" \
    "$BACKUP_ROOT"

backup_existing() {
    local source="$1"
    local relative="$2"

    if [ ! -f "$source" ] && [ ! -L "$source" ]; then
        return 0
    fi
    if [ -z "$BACKUP_DIR" ]; then
        BACKUP_DIR="$(mktemp -d "$BACKUP_ROOT/gnome-session-$STAMP-XXXXXX")"
    fi
    mkdir -p "$BACKUP_DIR/$(dirname "$relative")"
    cp -pP -- "$source" "$BACKUP_DIR/$relative"
}

backup_existing "$AUTOSTART_DIR/GolfOne.desktop" ".config/autostart/GolfOne.desktop"
backup_existing "$APPLICATIONS_DIR/GolfOne.desktop" ".local/share/applications/GolfOne.desktop"
backup_existing "$DESKTOP_DIR/GolfOne.desktop" "Desktop/GolfOne.desktop"

install -m 0644 "$AUTOSTART_TEMP" "$AUTOSTART_DIR/GolfOne.desktop"
install -m 0644 "$DESKTOP_TEMP" "$APPLICATIONS_DIR/GolfOne.desktop"
install -m 0755 "$DESKTOP_TEMP" "$DESKTOP_DIR/GolfOne.desktop"

if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_DIR/GolfOne.desktop" metadata::trusted true >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

echo "Golf One GNOME autostart and recovery launchers installed."
if [ -n "$BACKUP_DIR" ]; then
    echo "Previous launchers backed up to: $BACKUP_DIR"
fi
