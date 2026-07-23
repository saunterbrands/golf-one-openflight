#!/bin/bash
#
# Install the Golf One Plymouth theme and suppress Raspberry Pi boot branding.
# Run on the Raspberry Pi; this script intentionally requires root.
#

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo:" >&2
    echo "  sudo $0" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THEME_SOURCE="$SCRIPT_DIR/plymouth/golf-one"
THEME_TARGET="/usr/share/plymouth/themes/golf-one"
BOOT_DIR="/boot/firmware"
CONFIG_FILE="$BOOT_DIR/config.txt"
CMDLINE_FILE="$BOOT_DIR/cmdline.txt"
BACKUP_DIR="/var/backups/golf-one/boot-splash-$(date +%Y%m%d-%H%M%S)"

for required in \
    "$THEME_SOURCE/golf-one.plymouth" \
    "$THEME_SOURCE/golf-one.script" \
    "$THEME_SOURCE/splash.png" \
    "$CONFIG_FILE" \
    "$CMDLINE_FILE"; do
    if [ ! -f "$required" ]; then
        echo "Missing required file: $required" >&2
        exit 1
    fi
done

install -d -m 0755 "$BACKUP_DIR"
cp -a /etc/plymouth/plymouthd.conf "$BACKUP_DIR/plymouthd.conf"
cp -a "$CONFIG_FILE" "$BACKUP_DIR/config.txt"
cp -a "$CMDLINE_FILE" "$BACKUP_DIR/cmdline.txt"
for initramfs in "$BOOT_DIR"/initramfs* /boot/initrd.img-*; do
    if [ -f "$initramfs" ]; then
        cp -a "$initramfs" "$BACKUP_DIR/"
    fi
done

install -d -m 0755 "$THEME_TARGET"
install -m 0644 "$THEME_SOURCE/golf-one.plymouth" "$THEME_TARGET/golf-one.plymouth"
install -m 0644 "$THEME_SOURCE/golf-one.script" "$THEME_TARGET/golf-one.script"
install -m 0644 "$THEME_SOURCE/splash.png" "$THEME_TARGET/splash.png"

if ! grep -Eq '^[[:space:]]*disable_splash=1[[:space:]]*$' "$CONFIG_FILE"; then
    printf '\n# Golf One appliance boot branding\ndisable_splash=1\n' >> "$CONFIG_FILE"
fi

cmdline="$(tr '\n' ' ' < "$CMDLINE_FILE" | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//')"
for option in logo.nologo vt.global_cursor_default=0 loglevel=3; do
    case " $cmdline " in
        *" $option "*) ;;
        *) cmdline="$cmdline $option" ;;
    esac
done
printf '%s\n' "$cmdline" > "$CMDLINE_FILE"

/usr/sbin/plymouth-set-default-theme golf-one
/usr/sbin/update-initramfs -u -k all

echo
echo "Golf One boot theme installed."
echo "Backup: $BACKUP_DIR"
echo "Theme: $(/usr/sbin/plymouth-set-default-theme)"
echo "Reboot when ready to verify the physical splash."
