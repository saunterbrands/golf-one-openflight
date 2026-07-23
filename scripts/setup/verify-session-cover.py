#!/usr/bin/env python3
"""Verify that a compositor screenshot contains the Golf One cover image."""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_MEAN_CHANNEL_ERROR = 8.0
MAX_LARGE_ERROR_FRACTION = 0.02
LARGE_ERROR_THRESHOLD = 24


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    distances = (
        (abs(estimate - left), left),
        (abs(estimate - above), above),
        (abs(estimate - upper_left), upper_left),
    )
    return min(distances, key=lambda item: item[0])[1]


def _decode_rgb(path: Path) -> tuple[tuple[int, int], bytes]:
    payload = path.read_bytes()
    if not payload.startswith(PNG_SIGNATURE):
        raise ValueError(f"{path} is not a PNG")

    offset = len(PNG_SIGNATURE)
    compressed = bytearray()
    width = height = bit_depth = color_type = interlace = None
    while offset < len(payload):
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        chunk_data = payload[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    if bit_depth != 8 or color_type not in (2, 6) or interlace != 0:
        raise ValueError(
            f"{path} must be a non-interlaced 8-bit RGB or RGBA PNG"
        )
    if width is None or height is None:
        raise ValueError(f"{path} has no PNG header")

    channels = 3 if color_type == 2 else 4
    row_size = width * channels
    scanlines = zlib.decompress(bytes(compressed))
    expected_size = height * (row_size + 1)
    if len(scanlines) != expected_size:
        raise ValueError(f"{path} has an unexpected decoded size")

    previous = bytearray(row_size)
    rgb = bytearray(width * height * 3)
    source_offset = 0
    target_offset = 0
    for _ in range(height):
        filter_type = scanlines[source_offset]
        source_offset += 1
        if filter_type not in range(5):
            raise ValueError(f"{path} uses an unsupported PNG filter")
        encoded = scanlines[source_offset : source_offset + row_size]
        source_offset += row_size
        decoded = bytearray(row_size)

        for index, encoded_value in enumerate(encoded):
            left = decoded[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            value = encoded_value
            if filter_type == 1:
                value += left
            elif filter_type == 2:
                value += above
            elif filter_type == 3:
                value += (left + above) // 2
            elif filter_type == 4:
                value += _paeth(left, above, upper_left)
            decoded[index] = value % 256

        for pixel_offset in range(0, row_size, channels):
            rgb[target_offset : target_offset + 3] = decoded[
                pixel_offset : pixel_offset + 3
            ]
            target_offset += 3
        previous = decoded

    return (width, height), bytes(rgb)


def verify_cover(expected_path: Path, screenshot_path: Path) -> None:
    expected_size, expected = _decode_rgb(expected_path)
    screenshot_size, screenshot = _decode_rgb(screenshot_path)
    if screenshot_size != expected_size:
        raise ValueError(
            f"screenshot size {screenshot_size} does not match cover {expected_size}"
        )

    total_error = 0
    large_errors = 0
    for expected_channel, screenshot_channel in zip(
        expected, screenshot, strict=True
    ):
        error = abs(expected_channel - screenshot_channel)
        total_error += error
        if error > LARGE_ERROR_THRESHOLD:
            large_errors += 1

    mean_error = total_error / len(expected)
    large_error_fraction = large_errors / len(expected)
    if (
        mean_error > MAX_MEAN_CHANNEL_ERROR
        or large_error_fraction > MAX_LARGE_ERROR_FRACTION
    ):
        raise ValueError(
            "captured pixels do not match the Golf One cover "
            f"(mean error {mean_error:.2f}, "
            f"large-error fraction {large_error_fraction:.4f})"
        )


def main() -> int:
    if len(sys.argv) != 3:
        print(
            f"Usage: {Path(sys.argv[0]).name} EXPECTED.png SCREENSHOT.png",
            file=sys.stderr,
        )
        return 2
    try:
        verify_cover(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, zlib.error) as exc:
        print(f"Golf One cover verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
