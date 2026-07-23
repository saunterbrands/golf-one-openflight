#!/bin/bash
#
# Build the official FUSE practice range into appliance-local storage.
#
# FUSE is intentionally not vendored into the Golf One repository. Its
# PolyForm Noncommercial license permits this personal prototype; commercial
# Golf One distribution requires a separate license from OpenGolfSim.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FUSE_REPOSITORY="https://github.com/OpenGolfSim/fuse.git"
FUSE_COMMIT="6f10092c4444a538dd869d495eb2cb45697a5fb5"
INSTALL_ROOT="${GOLF_ONE_OFFLINE_FUSE_INSTALL_ROOT:-$HOME/.local/share/golf-one/fuse}"
VERSION_DIR="$INSTALL_ROOT/$FUSE_COMMIT"
CURRENT_LINK="$INSTALL_ROOT/current"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/golf-one-fuse.XXXXXX")"
SOURCE_DIR="$BUILD_ROOT/source"
OUTPUT_DIR="$BUILD_ROOT/dist/examples"
STAGING_DIR="$INSTALL_ROOT/.${FUSE_COMMIT}.staging.$$"

cleanup() {
    rm -rf "$BUILD_ROOT"
    if [ -d "$STAGING_DIR" ]; then
        rm -rf "$STAGING_DIR"
    fi
}
trap cleanup EXIT

for required_tool in git npm; do
    if ! command -v "$required_tool" >/dev/null 2>&1; then
        echo "$required_tool is required to install the offline practice range." >&2
        exit 1
    fi
done

mkdir -p "$INSTALL_ROOT"

if [ ! -f "$VERSION_DIR/examples/range/index.html" ]; then
    git init -q "$SOURCE_DIR"
    git -C "$SOURCE_DIR" remote add origin "$FUSE_REPOSITORY"
    git -C "$SOURCE_DIR" fetch -q --depth 1 origin "$FUSE_COMMIT"
    git -C "$SOURCE_DIR" checkout -q --detach FETCH_HEAD

    (
        cd "$SOURCE_DIR"
        npm ci --ignore-scripts
    )
    FUSE_SOURCE_DIR="$SOURCE_DIR" \
    FUSE_OUTPUT_DIR="$OUTPUT_DIR" \
        "$SOURCE_DIR/node_modules/.bin/vite" build \
        --config "$SCRIPT_DIR/offline-fuse-range.vite.config.mjs"

    mkdir -p "$STAGING_DIR/examples"
    cp -R "$OUTPUT_DIR/." "$STAGING_DIR/examples/"
    install -m 0644 "$SOURCE_DIR/LICENSE.md" "$STAGING_DIR/LICENSE.md"
    printf '%s\n' "$FUSE_COMMIT" > "$STAGING_DIR/SOURCE_COMMIT"
    printf '%s\n' "$FUSE_REPOSITORY" > "$STAGING_DIR/SOURCE_REPOSITORY"
    mv "$STAGING_DIR" "$VERSION_DIR"
fi

ln -sfn "$VERSION_DIR" "$CURRENT_LINK"

echo "Offline FUSE Practice Range installed."
echo "Source commit: $FUSE_COMMIT"
echo "Runtime path: $CURRENT_LINK/examples/range/index.html"
echo "License: $CURRENT_LINK/LICENSE.md"
