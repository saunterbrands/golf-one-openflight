"""Contracts for the Golf One Raspberry Pi boot branding."""

import struct
import zlib
from pathlib import Path


def _png_size_and_first_pixel(path: Path) -> tuple[tuple[int, int], tuple[int, int, int, int]]:
    """Read the dimensions and upper-left RGBA pixel from an 8-bit PNG."""
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
    assert scanlines[0] in range(5)
    # The first pixel has no left or upper neighbor, so all PNG filters reduce
    # to the four literal RGBA bytes that follow the row's filter byte.
    first_pixel = tuple(scanlines[1:5])
    return (width, height), first_pixel


def test_waveshare_boot_splash_uses_golf_one_green_and_native_orientation():
    repo_root = Path(__file__).resolve().parents[1]
    splash = repo_root / "scripts/setup/plymouth/golf-one/splash.png"

    size, first_pixel = _png_size_and_first_pixel(splash)

    assert size == (720, 1920)
    assert first_pixel == (0x17, 0x3A, 0x30, 0xFF)


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
