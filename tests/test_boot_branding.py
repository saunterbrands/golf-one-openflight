"""Contracts for the Golf One Raspberry Pi boot branding."""

import struct
import zlib
from pathlib import Path


def _paeth_predictor(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def _png_rgba_rows(path: Path) -> tuple[tuple[int, int], list[bytes]]:
    """Decode the rows of a non-interlaced, 8-bit RGBA PNG."""
    payload = path.read_bytes()
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")

    offset = 8
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

    assert (bit_depth, color_type, interlace) == (8, 6, 0)
    scanlines = zlib.decompress(bytes(compressed))
    bytes_per_pixel = 4
    row_size = width * bytes_per_pixel
    rows: list[bytes] = []
    previous = bytearray(row_size)
    offset = 0

    for _ in range(height):
        filter_type = scanlines[offset]
        assert filter_type in range(5)
        offset += 1
        encoded = scanlines[offset : offset + row_size]
        offset += row_size
        decoded = bytearray(row_size)

        for index, value in enumerate(encoded):
            left = decoded[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            above = previous[index]
            upper_left = (
                previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            )
            if filter_type == 1:
                value += left
            elif filter_type == 2:
                value += above
            elif filter_type == 3:
                value += (left + above) // 2
            elif filter_type == 4:
                value += _paeth_predictor(left, above, upper_left)
            decoded[index] = value % 256

        rows.append(bytes(decoded))
        previous = decoded

    return (width, height), rows


def test_waveshare_boot_splash_uses_golf_one_green_and_native_framebuffer_size():
    repo_root = Path(__file__).resolve().parents[1]
    splash = repo_root / "scripts/setup/plymouth/golf-one/splash.png"

    size, rows = _png_rgba_rows(splash)

    assert size == (720, 1920)
    assert tuple(rows[0][:4]) == (0x17, 0x3A, 0x30, 0xFF)


def test_waveshare_boot_splash_is_pre_rotated_for_physical_panel_orientation():
    """The native boot framebuffer is opposite the compositor's mounted view."""
    repo_root = Path(__file__).resolve().parents[1]
    splash = repo_root / "scripts/setup/plymouth/golf-one/splash.png"

    (width, height), rows = _png_rgba_rows(splash)
    lime_rows = [
        y
        for y, row in enumerate(rows)
        for x in range(width)
        if tuple(row[x * 4 : x * 4 + 4]) == (146, 213, 71, 255)
    ]
    wordmark_rows = [
        y
        for y, row in enumerate(rows)
        for x in range(width)
        if tuple(row[x * 4 : x * 4 + 4]) == (243, 243, 243, 255)
    ]

    assert lime_rows
    assert wordmark_rows
    assert min(lime_rows) > max(wordmark_rows)


def test_plymouth_installer_selects_and_embeds_the_golf_one_theme():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (
        repo_root / "scripts/setup/install-golf-one-plymouth.sh"
    ).read_text(encoding="utf-8")
    theme_script = (
        repo_root / "scripts/setup/plymouth/golf-one/golf-one.script"
    ).read_text(encoding="utf-8")

    assert "/usr/sbin/plymouth-set-default-theme golf-one" in installer
    assert "/usr/sbin/update-initramfs -u -k all" in installer
    assert "disable_splash=1" in installer
    assert "logo.nologo" in installer
    assert "vt.global_cursor_default=0" in installer
    assert "Window.SetBackgroundTopColor(0.090, 0.227, 0.188);" in theme_script
    assert "Window.SetBackgroundBottomColor(0.090, 0.227, 0.188);" in theme_script
