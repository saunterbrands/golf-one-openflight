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
FUSE_PROFILE="${GOLF_ONE_FUSE_PROFILE:-auto}"
DEVICE_MODEL_PATH="${GOLF_ONE_DEVICE_MODEL_PATH:-/proc/device-tree/model}"

if [ "$FUSE_PROFILE" = "auto" ]; then
    if [ -r "$DEVICE_MODEL_PATH" ] \
        && tr -d '\0' < "$DEVICE_MODEL_PATH" | grep -q "Raspberry Pi 5"; then
        FUSE_PROFILE="pi-balanced"
    else
        FUSE_PROFILE="full"
    fi
fi

case "$FUSE_PROFILE" in
    full)
        FUSE_VARIANT="range-explicit-webgl-v1"
        ;;
    pi-balanced)
        FUSE_VARIANT="range-explicit-webgl-anisotropy4-v3"
        ;;
    *)
        echo "Unsupported FUSE profile: $FUSE_PROFILE (choose auto, full, or pi-balanced)." >&2
        exit 1
        ;;
esac

VERSION_ID="${FUSE_COMMIT}-${FUSE_VARIANT}"
INSTALL_ROOT="${GOLF_ONE_OFFLINE_FUSE_INSTALL_ROOT:-$HOME/.local/share/golf-one/fuse}"
VERSION_DIR="$INSTALL_ROOT/$VERSION_ID"
CURRENT_LINK="$INSTALL_ROOT/current"
PREVIOUS_LINK="$INSTALL_ROOT/previous"
FUSE_PATCH="$SCRIPT_DIR/patches/fuse-$VERSION_ID.patch"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/golf-one-fuse.XXXXXX")"
SOURCE_DIR="$BUILD_ROOT/source"
OUTPUT_DIR="$BUILD_ROOT/dist/examples"
STAGING_DIR="$INSTALL_ROOT/.${VERSION_ID}.staging.$$"
ACTIVATION_LINK="$INSTALL_ROOT/.current.${VERSION_ID}.$$"

cleanup() {
    rm -rf "$BUILD_ROOT"
    if [ -d "$STAGING_DIR" ]; then
        rm -rf "$STAGING_DIR"
    fi
    if [ -L "$ACTIVATION_LINK" ]; then
        rm "$ACTIVATION_LINK"
    fi
}
trap cleanup EXIT

for required_tool in git npm sha256sum; do
    if ! command -v "$required_tool" >/dev/null 2>&1; then
        echo "$required_tool is required to install the offline practice range." >&2
        exit 1
    fi
done

if [ ! -f "$FUSE_PATCH" ]; then
    echo "Required FUSE source patch is missing: $FUSE_PATCH" >&2
    exit 1
fi

PATCH_SHA256="$(sha256sum "$FUSE_PATCH" | awk '{print $1}')"
mkdir -p "$INSTALL_ROOT"

if [ -e "$VERSION_DIR" ]; then
    if [ ! -f "$VERSION_DIR/examples/range/index.html" ] \
        || [ "$(cat "$VERSION_DIR/SOURCE_COMMIT" 2>/dev/null || true)" != "$FUSE_COMMIT" ] \
        || [ "$(cat "$VERSION_DIR/BUILD_VARIANT" 2>/dev/null || true)" != "$FUSE_VARIANT" ] \
        || [ "$(cat "$VERSION_DIR/SOURCE_PATCH_SHA256" 2>/dev/null || true)" != "$PATCH_SHA256" ]; then
        echo "Existing FUSE variant is incomplete or does not match its guarded source patch:" >&2
        echo "  $VERSION_DIR" >&2
        echo "Refusing to overwrite it. Bump FUSE_VARIANT or move the directory aside." >&2
        exit 1
    fi
else
    git init -q "$SOURCE_DIR"
    git -C "$SOURCE_DIR" remote add origin "$FUSE_REPOSITORY"
    git -C "$SOURCE_DIR" fetch -q --depth 1 origin "$FUSE_COMMIT"
    git -C "$SOURCE_DIR" checkout -q --detach FETCH_HEAD

    ACTUAL_FUSE_COMMIT="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
    if [ "$ACTUAL_FUSE_COMMIT" != "$FUSE_COMMIT" ]; then
        echo "FUSE checkout mismatch: expected $FUSE_COMMIT, got $ACTUAL_FUSE_COMMIT" >&2
        exit 1
    fi

    # Fail closed if the pinned upstream source no longer has the exact
    # renderer context that was benchmarked on the Pi 5 and Orange Pi 5.
    git -C "$SOURCE_DIR" apply --unidiff-zero --check "$FUSE_PATCH"
    git -C "$SOURCE_DIR" apply --unidiff-zero "$FUSE_PATCH"
    git -C "$SOURCE_DIR" diff --check

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
    printf '%s\n' "$FUSE_VARIANT" > "$STAGING_DIR/BUILD_VARIANT"
    printf '%s\n' "$PATCH_SHA256" > "$STAGING_DIR/SOURCE_PATCH_SHA256"
    mv "$STAGING_DIR" "$VERSION_DIR"
fi

if [ -L "$CURRENT_LINK" ]; then
    CURRENT_TARGET="$(readlink "$CURRENT_LINK")"
    if [ "$CURRENT_TARGET" != "$VERSION_DIR" ]; then
        if [ -e "$PREVIOUS_LINK" ] && [ ! -L "$PREVIOUS_LINK" ]; then
            echo "Rollback path exists but is not a symlink: $PREVIOUS_LINK" >&2
            exit 1
        fi
        ln -sfn "$CURRENT_TARGET" "$PREVIOUS_LINK"
    fi
elif [ -e "$CURRENT_LINK" ]; then
    echo "Current FUSE runtime path exists but is not a symlink: $CURRENT_LINK" >&2
    exit 1
fi

# Replace the active symlink atomically. The previous build directory remains
# untouched and, when one was active, is also retained through PREVIOUS_LINK.
ln -s "$VERSION_DIR" "$ACTIVATION_LINK"
if ! mv -Tf "$ACTIVATION_LINK" "$CURRENT_LINK" 2>/dev/null; then
    # BSD mv (used by macOS development hosts) spells no-dereference as -h.
    # GNU mv (used by the appliance) takes the -T branch above.
    mv -hf "$ACTIVATION_LINK" "$CURRENT_LINK"
fi

echo "Offline FUSE Practice Range installed."
echo "Source commit: $FUSE_COMMIT"
echo "Rendering profile: $FUSE_PROFILE"
echo "Build variant: $FUSE_VARIANT"
echo "Runtime path: $CURRENT_LINK/examples/range/index.html"
if [ -L "$PREVIOUS_LINK" ]; then
    echo "Rollback runtime: $PREVIOUS_LINK"
fi
echo "License: $CURRENT_LINK/LICENSE.md"
