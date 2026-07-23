#!/bin/sh
#
# LightDM entry point for the Golf One appliance session.
#
# A dedicated Labwc config directory deliberately avoids Raspberry Pi OS's
# merged autostart. The appliance startup wrapper can therefore cover the
# screen before the normal desktop is created behind the kiosk.
#

set -eu

if [ -r /usr/bin/setup_env ]; then
    # Raspberry Pi OS desktop environment defaults (menus, GTK, Qt, etc.).
    # shellcheck disable=SC1091
    . /usr/bin/setup_env
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SESSION_CONFIG_DIR="${GOLF_ONE_LABWC_CONFIG_DIR:-$HOME/.config/golf-one/labwc}"

export DESKTOP_SESSION=golf-one
export XDG_CURRENT_DESKTOP=labwc
export XDG_SESSION_DESKTOP=golf-one

exec /usr/bin/labwc \
    --config-dir "$SESSION_CONFIG_DIR" \
    --startup "$SCRIPT_DIR/run-appliance-session.sh"
