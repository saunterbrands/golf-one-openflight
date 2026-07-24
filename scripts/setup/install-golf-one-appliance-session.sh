#!/bin/bash
#
# Install the dedicated LightDM/Labwc Golf One appliance session.
#
# This requires root because it adds a Wayland session and updates LightDM's
# effective autologin session. A branded swaybg layer is the only boot-time
# recovery surface; Raspberry Pi Desktop starts only after the protected exit.
#

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo:" >&2
    echo "  sudo $0" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
TARGET_USER="${GOLF_ONE_APPLIANCE_USER:-${SUDO_USER:-openflight}}"
PASSWD_ENTRY="$(getent passwd "$TARGET_USER" || true)"

if [ -z "$PASSWD_ENTRY" ]; then
    echo "Golf One user does not exist: $TARGET_USER" >&2
    exit 1
fi

TARGET_HOME="$(printf '%s\n' "$PASSWD_ENTRY" | cut -d: -f6)"
TARGET_GROUP="$(id -gn "$TARGET_USER")"
SESSION_CONFIG_DIR="$TARGET_HOME/.config/golf-one/labwc"
AUTOSTART_DIR="$TARGET_HOME/.config/autostart"
AUTOTOUCH_TARGET="$AUTOSTART_DIR/autotouch.desktop"
APPLICATIONS_DIR="$TARGET_HOME/.local/share/applications"
DESKTOP_DIR="$TARGET_HOME/Desktop"
APPLICATION_TARGET="$APPLICATIONS_DIR/GolfOne.desktop"
DESKTOP_TARGET="$DESKTOP_DIR/GolfOne.desktop"
LIGHTDM_MAIN="/etc/lightdm/lightdm.conf"
LEGACY_LIGHTDM_TARGET="/etc/lightdm/lightdm.conf.d/90-golf-one-appliance.conf"
WAYLAND_TARGET="/usr/share/wayland-sessions/golf-one.desktop"
SESSION_COMMAND="/usr/local/bin/golf-one-appliance-session"
BACKUP_DIR="/var/backups/golf-one/appliance-session-$(date +%Y%m%d-%H%M%S)"
SYSTEM_LABWC_DIR="/etc/xdg/labwc"

for required in \
    "$SCRIPT_DIR/golf-one-wayland.desktop" \
    "$SCRIPT_DIR/autotouch.desktop" \
    "$SCRIPT_DIR/GolfOne.desktop" \
    "$SCRIPT_DIR/session-cover.png" \
    "$SCRIPT_DIR/verify-session-cover.py" \
    "$SCRIPT_DIR/kiosk-loading.html" \
    "$PROJECT_DIR/scripts/start-appliance-session-compositor.sh" \
    "$PROJECT_DIR/scripts/run-appliance-session.sh" \
    "$LIGHTDM_MAIN" \
    "$SYSTEM_LABWC_DIR/rc.xml"; do
    if [ ! -f "$required" ]; then
        echo "Missing required file: $required" >&2
        exit 1
    fi
done

if ! command -v xmlstarlet >/dev/null 2>&1; then
    echo "xmlstarlet is required to preserve Raspberry Pi Labwc settings." >&2
    exit 1
fi
if ! command -v swaybg >/dev/null 2>&1; then
    echo "swaybg is required for the branded appliance background." >&2
    echo "Install it with: sudo apt install swaybg" >&2
    exit 1
fi
if [ ! -x /usr/bin/grim ]; then
    echo "grim is required to verify the branded background on the display." >&2
    exit 1
fi
if ! /usr/bin/python3 -c 'import zlib' >/dev/null 2>&1; then
    echo "Python 3 with zlib is required to verify the branded background." >&2
    exit 1
fi
if [ ! -x /usr/bin/nc ]; then
    echo "OpenBSD netcat is required for the loading-page paint handshake." >&2
    exit 1
fi
if [ ! -x /usr/bin/setsid ]; then
    echo "util-linux setsid is required to isolate the branded cover process group." >&2
    exit 1
fi

LIGHTDM_BIN="$(command -v lightdm || true)"
if [ -z "$LIGHTDM_BIN" ]; then
    echo "LightDM is required to select the Golf One appliance session." >&2
    exit 1
fi

install -d -m 0755 "$BACKUP_DIR" /usr/share/wayland-sessions /usr/local/bin
cp -a "$LIGHTDM_MAIN" "$BACKUP_DIR/lightdm.conf"
if [ -e "$LEGACY_LIGHTDM_TARGET" ]; then
    cp -a "$LEGACY_LIGHTDM_TARGET" "$BACKUP_DIR/"
fi
if [ -f "$WAYLAND_TARGET" ]; then
    cp -a "$WAYLAND_TARGET" "$BACKUP_DIR/"
fi
if [ -e "$SESSION_COMMAND" ] || [ -L "$SESSION_COMMAND" ]; then
    cp -a "$SESSION_COMMAND" "$BACKUP_DIR/"
fi
if [ -d "$SESSION_CONFIG_DIR" ]; then
    cp -a "$SESSION_CONFIG_DIR" "$BACKUP_DIR/labwc"
fi
if [ -f "$AUTOTOUCH_TARGET" ]; then
    cp -a "$AUTOTOUCH_TARGET" "$BACKUP_DIR/autotouch.desktop"
fi
if [ -f "$APPLICATION_TARGET" ]; then
    cp -a "$APPLICATION_TARGET" "$BACKUP_DIR/GolfOne.application.desktop"
fi
if [ -f "$DESKTOP_TARGET" ]; then
    cp -a "$DESKTOP_TARGET" "$BACKUP_DIR/GolfOne.desktop"
fi

install -d -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0700 "$SESSION_CONFIG_DIR"
install -d -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0755 "$AUTOSTART_DIR"
install -d -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0755 \
    "$APPLICATIONS_DIR" "$DESKTOP_DIR"

RC_TEMP="$(mktemp)"
LIGHTDM_TEMP="$(mktemp)"
DESKTOP_TEMP="$(mktemp)"
trap 'rm -f "$RC_TEMP" "$LIGHTDM_TEMP" "$DESKTOP_TEMP"' EXIT
cp "$SYSTEM_LABWC_DIR/rc.xml" "$RC_TEMP"
cp "$LIGHTDM_MAIN" "$LIGHTDM_TEMP"
PROJECT_DIR_SED="$(printf '%s\n' "$PROJECT_DIR" | sed 's/[&|]/\\&/g')"
sed "s|@GOLF_ONE_PROJECT_DIR@|$PROJECT_DIR_SED|g" \
    "$SCRIPT_DIR/GolfOne.desktop" >"$DESKTOP_TEMP"
if grep -q '@GOLF_ONE_PROJECT_DIR@' "$DESKTOP_TEMP"; then
    echo "Could not render the Golf One desktop launcher." >&2
    exit 1
fi

set_lightdm_seat_key() {
    local key="$1"
    local value="$2"
    local source="$3"
    local output

    output="$(mktemp)"
    if grep -Eq "^[[:space:]]*$key[[:space:]]*=" "$source"; then
        sed -E \
            "s|^[[:space:]]*$key[[:space:]]*=.*$|$key=$value|" \
            "$source" >"$output"
    else
        awk -v key="$key" -v value="$value" '
            BEGIN { inserted = 0 }
            /^\[Seat:\*\][[:space:]]*$/ && !inserted {
                print
                print key "=" value
                inserted = 1
                next
            }
            { print }
            END {
                if (!inserted) {
                    print ""
                    print "[Seat:*]"
                    print key "=" value
                }
            }
        ' "$source" >"$output"
    fi
    mv "$output" "$source"
}

set_lightdm_seat_key autologin-user "$TARGET_USER" "$LIGHTDM_TEMP"
set_lightdm_seat_key autologin-session golf-one "$LIGHTDM_TEMP"

xmlstarlet ed -P -L \
    -N labwc="http://openbox.org/3.4/rc" \
    -d '/labwc:openbox_config/labwc:touch[contains(@deviceName, "Goodix Capacitive TouchScreen")]' \
    -d '/labwc:openbox_config/labwc:libinput/labwc:device[@category="touch"]' \
    -d '/labwc:openbox_config/labwc:libinput/labwc:device[contains(@category, "Goodix Capacitive TouchScreen")]' \
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
        -n category -v 'touch' \
    -s '/labwc:openbox_config/labwc:libinput[last()]/device' -t elem \
        -n calibrationMatrix -v '0 -1 1 1 0 0' \
    "$RC_TEMP"
xmlstarlet val -w "$RC_TEMP" >/dev/null

TOUCH_DEVICE_COUNT="$(xmlstarlet sel \
    -N labwc="http://openbox.org/3.4/rc" \
    -t -v 'count(/labwc:openbox_config/labwc:libinput/labwc:device[@category="touch"])' \
    "$RC_TEMP")"
LEGACY_GOODIX_TOUCH_COUNT="$(xmlstarlet sel \
    -N labwc="http://openbox.org/3.4/rc" \
    -t -v 'count(/labwc:openbox_config/labwc:touch[contains(@deviceName, "Goodix Capacitive TouchScreen")])' \
    "$RC_TEMP")"
TOUCH_MAP_COUNT="$(xmlstarlet sel \
    -N labwc="http://openbox.org/3.4/rc" \
    -t -v 'count(/labwc:openbox_config/labwc:libinput/labwc:device[@category="touch"]/labwc:mapToOutput)' \
    "$RC_TEMP")"
TOUCH_MATRIX="$(xmlstarlet sel \
    -N labwc="http://openbox.org/3.4/rc" \
    -t -v '/labwc:openbox_config/labwc:libinput/labwc:device[@category="touch"]/labwc:calibrationMatrix' \
    "$RC_TEMP")"
if [ "$TOUCH_DEVICE_COUNT" != "1" ] \
    || [ "$LEGACY_GOODIX_TOUCH_COUNT" != "0" ] \
    || [ "$TOUCH_MAP_COUNT" != "0" ] \
    || [ "$TOUCH_MATRIX" != "0 -1 1 1 0 0" ]; then
    echo "Generated Labwc touch calibration failed validation." >&2
    exit 1
fi

install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0644 \
    "$RC_TEMP" "$SESSION_CONFIG_DIR/rc.xml"
if [ -f "$SYSTEM_LABWC_DIR/menu.xml" ]; then
    install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0644 \
        "$SYSTEM_LABWC_DIR/menu.xml" "$SESSION_CONFIG_DIR/menu.xml"
fi
if [ -f "$SYSTEM_LABWC_DIR/environment" ]; then
    install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0644 \
        "$SYSTEM_LABWC_DIR/environment" "$SESSION_CONFIG_DIR/environment"
fi
install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0644 \
    /dev/null "$SESSION_CONFIG_DIR/autostart"
install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0644 \
    "$SCRIPT_DIR/autotouch.desktop" "$AUTOTOUCH_TARGET"
install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0755 \
    "$DESKTOP_TEMP" "$APPLICATION_TARGET"
install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0755 \
    "$DESKTOP_TEMP" "$DESKTOP_TARGET"
if command -v gio >/dev/null 2>&1; then
    runuser -u "$TARGET_USER" -- \
        gio set "$DESKTOP_TARGET" metadata::trusted true >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    runuser -u "$TARGET_USER" -- \
        update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

install -m 0644 "$SCRIPT_DIR/golf-one-wayland.desktop" "$WAYLAND_TARGET"
chmod 0755 \
    "$PROJECT_DIR/scripts/start-appliance-session-compositor.sh" \
    "$PROJECT_DIR/scripts/run-appliance-session.sh"
rm -f "$SESSION_COMMAND"
ln -s "$PROJECT_DIR/scripts/start-appliance-session-compositor.sh" "$SESSION_COMMAND"
RESOLVED_SESSION_COMMAND="$(readlink -e "$SESSION_COMMAND" || true)"
if [ "$RESOLVED_SESSION_COMMAND" != "$PROJECT_DIR/scripts/start-appliance-session-compositor.sh" ] \
    || [ ! -x "$RESOLVED_SESSION_COMMAND" ]; then
    echo "Installed Golf One session command does not resolve to an executable." >&2
    exit 1
fi

# LightDM reads /etc/lightdm/lightdm.conf after conf.d. Update the effective
# main file, then prove that no later source overrides the appliance session.
install -m 0644 "$LIGHTDM_TEMP" "$LIGHTDM_MAIN"
if [ -e "$LEGACY_LIGHTDM_TARGET" ]; then
    rm -f "$LEGACY_LIGHTDM_TARGET"
fi
if ! EFFECTIVE_LIGHTDM="$("$LIGHTDM_BIN" --show-config 2>&1)"; then
    install -m 0644 "$BACKUP_DIR/lightdm.conf" "$LIGHTDM_MAIN"
    echo "LightDM could not parse the Golf One config; restored the prior config." >&2
    printf '%s\n' "$EFFECTIVE_LIGHTDM" >&2
    "$LIGHTDM_BIN" --show-config >/dev/null 2>&1 || true
    exit 1
fi
if ! printf '%s\n' "$EFFECTIVE_LIGHTDM" \
    | grep -Eq "autologin-user=$TARGET_USER[[:space:]]*$" \
    || ! printf '%s\n' "$EFFECTIVE_LIGHTDM" \
        | grep -Eq 'autologin-session=golf-one[[:space:]]*$'; then
    install -m 0644 "$BACKUP_DIR/lightdm.conf" "$LIGHTDM_MAIN"
    echo "LightDM rejected the Golf One autologin session; restored the prior config." >&2
    printf '%s\n' "$EFFECTIVE_LIGHTDM" >&2
    "$LIGHTDM_BIN" --show-config >/dev/null 2>&1 || true
    exit 1
fi

rm -f "$RC_TEMP" "$LIGHTDM_TEMP" "$DESKTOP_TEMP"
trap - EXIT

echo
echo "Golf One appliance session installed."
echo "User: $TARGET_USER"
echo "Session: $WAYLAND_TARGET"
echo "LightDM effective session: golf-one"
echo "Backup: $BACKUP_DIR"
echo "Reboot to verify the Plymouth → Golf One cover → dashboard handoff."
