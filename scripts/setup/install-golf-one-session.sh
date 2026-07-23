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
if [ -f "$LABWC_DIR/rc.xml" ]; then
    cp "$LABWC_DIR/rc.xml" "$BACKUP_DIR/labwc-rc.$STAMP.xml"
fi

install -m 0644 "$SCRIPT_DIR/labwc-autostart" "$LABWC_DIR/autostart"

if [ ! -s "$LABWC_DIR/rc.xml" ]; then
    install -m 0644 "$SCRIPT_DIR/labwc-rc.xml" "$LABWC_DIR/rc.xml"
else
    if ! command -v xmlstarlet >/dev/null 2>&1; then
        echo "xmlstarlet is required to preserve and update an existing Labwc config." >&2
        exit 1
    fi

    RC_TEMP="$(mktemp "$LABWC_DIR/rc.xml.XXXXXX")"
    trap 'rm -f "$RC_TEMP"' EXIT
    cp "$LABWC_DIR/rc.xml" "$RC_TEMP"

    xmlstarlet ed -P -L \
        -N labwc="http://openbox.org/3.4/rc" \
        -d '/labwc:openbox_config/labwc:touch[@deviceName="Goodix Capacitive TouchScreen"]' \
        -d '/labwc:openbox_config/labwc:libinput/labwc:device[@category="Goodix Capacitive TouchScreen"]' \
        "$RC_TEMP"
    xmlstarlet ed -P -L \
        -N labwc="http://openbox.org/3.4/rc" \
        -d '/labwc:openbox_config/labwc:libinput[not(*)]' \
        "$RC_TEMP"

    LIBINPUT_COUNT="$(xmlstarlet sel \
        -N labwc="http://openbox.org/3.4/rc" \
        -t -v 'count(/labwc:openbox_config/labwc:libinput)' \
        "$RC_TEMP")"
    if [ "$LIBINPUT_COUNT" = "0" ]; then
        xmlstarlet ed -P -L \
            -N labwc="http://openbox.org/3.4/rc" \
            -s '/labwc:openbox_config' -t elem -n libinput -v '' \
            "$RC_TEMP"
    fi

    xmlstarlet ed -P -L \
        -N labwc="http://openbox.org/3.4/rc" \
        -s '/labwc:openbox_config/labwc:libinput[last()]' -t elem -n device -v '' \
        -i '/labwc:openbox_config/labwc:libinput[last()]/device' -t attr \
            -n category -v 'Goodix Capacitive TouchScreen' \
        -s '/labwc:openbox_config/labwc:libinput[last()]/device' -t elem \
            -n calibrationMatrix -v '0 -1 1 1 0 0' \
        "$RC_TEMP"
    xmlstarlet val -w "$RC_TEMP" >/dev/null
    install -m 0644 "$RC_TEMP" "$LABWC_DIR/rc.xml"
    rm -f "$RC_TEMP"
    trap - EXIT
fi

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
echo "Previous Labwc config backup: $BACKUP_DIR/labwc-rc.$STAMP.xml"
