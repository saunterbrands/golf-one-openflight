#!/bin/bash
#
# Install the unprivileged Golf One Labwc autostart and desktop recovery entry.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABWC_DIR="$HOME/.config/labwc"
APPLICATIONS_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$HOME/Desktop"
BACKUP_DIR="$HOME/.config/golf-one/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$LABWC_DIR" "$APPLICATIONS_DIR" "$DESKTOP_DIR" "$BACKUP_DIR"

if [ -f "$LABWC_DIR/autostart" ]; then
    cp "$LABWC_DIR/autostart" "$BACKUP_DIR/labwc-autostart.$STAMP"
fi

install -m 0644 "$SCRIPT_DIR/labwc-autostart" "$LABWC_DIR/autostart"
install -m 0755 "$SCRIPT_DIR/GolfOne.desktop" "$APPLICATIONS_DIR/GolfOne.desktop"
install -m 0755 "$SCRIPT_DIR/GolfOne.desktop" "$DESKTOP_DIR/GolfOne.desktop"

if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_DIR/GolfOne.desktop" metadata::trusted true >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

echo "Golf One Labwc autostart and desktop launcher installed."
echo "Previous Labwc autostart backup: $BACKUP_DIR/labwc-autostart.$STAMP"
