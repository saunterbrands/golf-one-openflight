"""Tests for the kiosk browser rendering-path configuration."""

import hashlib
import json
import os
import re
import struct
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def _bash_function_body(source, function_name):
    """Return a Bash function body without confusing it with its definition."""
    declaration = re.search(
        rf"(?m)^{re.escape(function_name)}\(\) \{{[ \t]*$",
        source,
    )
    assert declaration is not None, f"missing Bash function: {function_name}"

    body_start = declaration.end()
    body_end = body_start
    depth = 1
    for line in source[body_start:].splitlines(keepends=True):
        # Parameter expansions contain balanced braces, so tracking the net
        # brace depth remains sufficient for these shell scripts.
        depth += line.count("{") - line.count("}")
        if depth == 0:
            return source[body_start:body_end]
        body_end += len(line)

    raise AssertionError(f"unterminated Bash function: {function_name}")


def _apply_calibration(matrix, point):
    """Apply a six-value libinput calibration matrix to a normalized point."""
    a, b, c, d, e, f = matrix
    x, y = point
    return (a * x + b * y + c, d * x + e * y + f)


def _rotate_counterclockwise(point):
    """Model the quarter-turn mismatch reported on the installed display."""
    x, y = point
    return (y, 1 - x)


def test_kiosk_prefers_native_wayland_and_reduced_motion():
    repo_root = Path(__file__).resolve().parents[1]
    start_script = (repo_root / "scripts/start-kiosk.sh").read_text(encoding="utf-8")
    browser_script = (repo_root / "scripts/open-kiosk-browser.sh").read_text(encoding="utf-8")

    assert 'export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"' in start_script
    assert '"$SCRIPT_DIR/open-kiosk-browser.sh" "$KIOSK_URL" &' in start_script
    assert 'RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"' in browser_script
    assert 'for candidate in "$RUNTIME_DIR"/wayland-*' in browser_script
    assert '[ -S "$RUNTIME_DIR/$WAYLAND_SOCKET" ]' in browser_script
    assert "--ozone-platform=wayland" in browser_script
    assert "--ozone-platform=x11" in browser_script
    assert 'OZONE_PLATFORM="${GOLF_ONE_OZONE_PLATFORM:-auto}"' in browser_script
    assert (
        'FORCE_DEVICE_SCALE_FACTOR="${GOLF_ONE_FORCE_DEVICE_SCALE_FACTOR:-}"'
        in browser_script
    )
    assert "--force-prefers-reduced-motion" in browser_script
    assert "--password-store=basic" in browser_script
    assert "--user-data-dir=" in browser_script
    assert 'KIOSK_URL="${1:-http://localhost:8080/}"' in browser_script
    assert "?autolaunch=1" not in browser_script
    assert "--disable-extensions-except=" in browser_script
    assert "--load-extension=" in browser_script


def test_kiosk_fingerprints_extension_source_to_avoid_stale_service_workers():
    repo_root = Path(__file__).resolve().parents[1]
    browser_script = (repo_root / "scripts/open-kiosk-browser.sh").read_text(encoding="utf-8")

    assert "EXTENSION_FINGERPRINT" in browser_script
    assert "EXTENSION_RUNTIME_DIR" in browser_script
    assert 'sha256sum "$EXTENSION_DIR/manifest.json"' in browser_script
    assert '"--load-extension=$EXTENSION_RUNTIME_DIR"' in browser_script


def test_kiosk_rotates_stale_session_state_without_erasing_login_profile(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    browser_script = repo_root / "scripts/open-kiosk-browser.sh"
    profile = tmp_path / "profile"
    default = profile / "Default"
    sessions = default / "Sessions"
    sessions.mkdir(parents=True)
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    host = subprocess.run(
        ["hostname"], check=True, capture_output=True, text=True
    ).stdout.strip()
    (profile / "SingletonLock").symlink_to(f"{host}-999999")

    restore_state = {
        default / "Current Session": "current-session",
        default / "Current Tabs": "current-tabs",
        default / "Last Session": "last-session",
        default / "Last Tabs": "last-tabs",
        sessions / "Session_123": "new-session",
        sessions / "Tabs_123": "new-tabs",
    }
    for path, content in restore_state.items():
        path.write_text(content, encoding="utf-8")

    preserved_state = {
        default / "Cookies": "saved-login-cookie",
        default / "Login Data": "saved-password",
        default / "Preferences": "saved-preferences",
        profile / "Local State": "saved-local-state",
    }
    for path, content in preserved_state.items():
        path.write_text(content, encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    chromium = fake_bin / "chromium"
    chromium.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$GOLF_ONE_BROWSER_ARGS_FILE"\n',
        encoding="utf-8",
    )
    chromium.chmod(0o755)

    args_file = tmp_path / "chromium-args"
    backup_root = tmp_path / "session-backups"
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    requested_url = "http://localhost:8080/"
    env = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "GOLF_ONE_BROWSER_PROFILE_DIR": str(profile),
        "GOLF_ONE_BROWSER_SESSION_BACKUP_DIR": str(backup_root),
        "GOLF_ONE_BROWSER_EXTENSION_DIR": str(tmp_path / "no-extension"),
        "GOLF_ONE_BROWSER_PROC_ROOT": str(proc_root),
        "GOLF_ONE_BROWSER_ARGS_FILE": str(args_file),
        "XDG_RUNTIME_DIR": str(runtime_dir),
    }

    subprocess.run(
        ["bash", str(browser_script), requested_url],
        check=True,
        env=env,
        text=True,
        capture_output=True,
    )

    backups = list(backup_root.iterdir())
    assert len(backups) == 1
    backup = backups[0]
    for original, content in restore_state.items():
        assert not original.exists()
        relative = original.relative_to(profile)
        assert (backup / relative).read_text(encoding="utf-8") == content

    for path, content in preserved_state.items():
        assert path.read_text(encoding="utf-8") == content
        assert not (backup / path.relative_to(profile)).exists()

    chromium_args = args_file.read_text(encoding="utf-8").splitlines()
    assert chromium_args[-1] == requested_url


def test_kiosk_does_not_move_session_files_owned_by_live_profile_browser(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    browser_script = repo_root / "scripts/open-kiosk-browser.sh"
    profile = tmp_path / "profile"
    sessions = profile / "Default" / "Sessions"
    sessions.mkdir(parents=True)
    session_state = sessions / "Session_456"
    session_state.write_text("live-session", encoding="utf-8")

    proc_root = tmp_path / "proc"
    browser_pid = 424242
    browser_proc = proc_root / str(browser_pid)
    browser_proc.mkdir(parents=True)
    (browser_proc / "status").write_text(
        f"Name:\tchromium\nUid:\t{os.getuid()}\t{os.getuid()}\t{os.getuid()}\t{os.getuid()}\n",
        encoding="utf-8",
    )
    (browser_proc / "cmdline").write_bytes(
        b"/usr/lib/chromium/chromium\0"
        + f"--user-data-dir={profile}".encode()
        + b"\0"
    )
    (browser_proc / "exe").symlink_to("/usr/lib/chromium/chromium")
    host = subprocess.run(
        ["hostname"], check=True, capture_output=True, text=True
    ).stdout.strip()
    (profile / "SingletonLock").symlink_to(f"{host}-{browser_pid}")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    chromium = fake_bin / "chromium"
    chromium.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$GOLF_ONE_BROWSER_ARGS_FILE"\n',
        encoding="utf-8",
    )
    chromium.chmod(0o755)

    args_file = tmp_path / "chromium-args"
    backup_root = tmp_path / "session-backups"
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    requested_url = "http://localhost:8080/"
    env = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "GOLF_ONE_BROWSER_PROFILE_DIR": str(profile),
        "GOLF_ONE_BROWSER_SESSION_BACKUP_DIR": str(backup_root),
        "GOLF_ONE_BROWSER_EXTENSION_DIR": str(tmp_path / "no-extension"),
        "GOLF_ONE_BROWSER_PROC_ROOT": str(proc_root),
        "GOLF_ONE_BROWSER_ARGS_FILE": str(args_file),
        "XDG_RUNTIME_DIR": str(runtime_dir),
    }

    result = subprocess.run(
        ["bash", str(browser_script), requested_url],
        check=True,
        env=env,
        text=True,
        capture_output=True,
    )

    assert session_state.read_text(encoding="utf-8") == "live-session"
    assert not backup_root.exists()
    assert "profile is already live" in result.stdout
    chromium_args = args_file.read_text(encoding="utf-8").splitlines()
    assert chromium_args[-1] == requested_url


def test_kiosk_can_pin_measured_x11_path_and_device_scale(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    browser_script = repo_root / "scripts/open-kiosk-browser.sh"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    chromium = fake_bin / "chromium"
    chromium.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$GOLF_ONE_BROWSER_ARGS_FILE"\n',
        encoding="utf-8",
    )
    chromium.chmod(0o755)

    args_file = tmp_path / "chromium-args"
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    env = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "GOLF_ONE_BROWSER_PROFILE_DIR": str(tmp_path / "profile"),
        "GOLF_ONE_BROWSER_EXTENSION_DIR": str(tmp_path / "no-extension"),
        "GOLF_ONE_BROWSER_ARGS_FILE": str(args_file),
        "GOLF_ONE_OZONE_PLATFORM": "x11",
        "GOLF_ONE_FORCE_DEVICE_SCALE_FACTOR": "1",
        "XDG_RUNTIME_DIR": str(runtime_dir),
    }

    subprocess.run(
        ["bash", str(browser_script), "http://localhost:8080/"],
        check=True,
        env=env,
        text=True,
        capture_output=True,
    )

    args = args_file.read_text(encoding="utf-8").splitlines()
    assert "--ozone-platform=x11" in args
    assert "--ozone-platform=wayland" not in args
    assert "--force-device-scale-factor=1" in args


def test_desktop_recovery_launcher_reuses_live_server_or_starts_simulator():
    repo_root = Path(__file__).resolve().parents[1]
    launcher = (repo_root / "scripts/launch-golf-one.sh").read_text(encoding="utf-8")
    desktop = (repo_root / "scripts/setup/GolfOne.desktop").read_text(encoding="utf-8")

    assert 'HEALTH_URL="${GOLF_ONE_SERVER_HEALTH_URL:-http://localhost:8080}"' in launcher
    assert "curl -fsS" in launcher
    assert 'exec "$SCRIPT_DIR/open-kiosk-browser.sh" "$KIOSK_URL"' in launcher
    assert 'KIOSK_URL="${GOLF_ONE_KIOSK_URL:-http://localhost:8080/}"' in launcher
    assert "?autolaunch=1" not in launcher
    assert "DEFAULT_ARGS=(--mock --sim)" in launcher
    assert "udevadm info -q property" in launcher
    assert "ID_VENDOR_ID=0483" in launcher
    assert "ID_VENDOR_ID=058b" in launcher
    assert "ID_MODEL_ID=0058" in launcher
    assert "GOLF_ONE_RADAR_PORT" in launcher
    assert 'compgen -G "/dev/ttyACM*"' not in launcher
    assert "DEFAULT_ARGS=(--sim)" in launcher
    assert "flock -n 9" in launcher
    assert "Name=Golf One" in desktop
    assert "Exec=@GOLF_ONE_PROJECT_DIR@/scripts/launch-golf-one.sh" in desktop
    assert "Icon=@GOLF_ONE_PROJECT_DIR@/ui/public/golfone-icon.svg" in desktop
    assert "--mock" not in desktop


def test_gnome_x11_autostart_uses_branded_loading_browser_and_focus_wrapper():
    repo_root = Path(__file__).resolve().parents[1]
    wrapper = (repo_root / "scripts/launch-golf-one-gnome.sh").read_text(
        encoding="utf-8"
    )
    browser = (repo_root / "scripts/open-kiosk-browser.sh").read_text(
        encoding="utf-8"
    )
    autostart = (
        repo_root / "scripts/setup/GolfOneGnomeAutostart.desktop"
    ).read_text(encoding="utf-8")

    main_body = _bash_function_body(wrapper, "main")
    ready_listener = main_body.index("start_loading_page_ready_server")
    loading_browser = main_body.index('"$BROWSER_SCRIPT" "$BOOT_PAGE_URL"')
    dashboard = main_body.index('"$LAUNCH_SCRIPT" "$@"', loading_browser)
    assert ready_listener < loading_browser < dashboard
    assert 'BOOT_PAGE="$PROJECT_DIR/scripts/setup/kiosk-loading.html"' in wrapper
    assert 'BOOT_PAGE_URL="file://$BOOT_PAGE#$KIOSK_URL"' in wrapper
    assert "PAGE_READY_PORT=38917" in wrapper
    assert "GOLF_ONE_BROWSER_ALREADY_RUNNING=1" in main_body
    assert 'xdotool search --onlyvisible --class "$WINDOW_CLASS"' in wrapper
    assert "xdotool key --clearmodifiers Escape" in wrapper
    assert 'xdotool windowactivate --sync "$window_id"' in wrapper
    assert 'xdotool windowfocus "$window_id"' in wrapper

    platform_branch = browser[
        browser.index('if [ "$OZONE_PLATFORM" = "wayland" ]') :
    ]
    wayland_branch, x11_branch = platform_branch.split("\nelse\n", 1)
    assert "--class=GolfOneKiosk" not in wayland_branch
    assert "--class=GolfOneKiosk" in x11_branch
    assert "OnlyShowIn=GNOME;" in autostart
    assert (
        "Exec=@GOLF_ONE_PROJECT_DIR@/scripts/launch-golf-one-gnome.sh" in autostart
    )
    assert 'GOLF_ONE_OZONE_PLATFORM="${GOLF_ONE_OZONE_PLATFORM:-x11}"' in wrapper
    assert (
        'GOLF_ONE_FORCE_DEVICE_SCALE_FACTOR="${GOLF_ONE_FORCE_DEVICE_SCALE_FACTOR:-1}"'
        in wrapper
    )


def test_gnome_wrapper_falls_back_to_normal_launcher_outside_x11(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    wrapper = repo_root / "scripts/launch-golf-one-gnome.sh"
    launcher = tmp_path / "launcher"
    args_file = tmp_path / "launcher-args"
    launcher.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$GOLF_ONE_TEST_ARGS"\nexit 23\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)

    env = os.environ | {
        "GOLF_ONE_LAUNCH_SCRIPT": str(launcher),
        "GOLF_ONE_TEST_ARGS": str(args_file),
        "XDG_CURRENT_DESKTOP": "GNOME",
        "XDG_SESSION_TYPE": "wayland",
        "DISPLAY": ":99",
    }
    result = subprocess.run(
        ["bash", str(wrapper), "--mock", "--sim"],
        check=False,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 23
    assert args_file.read_text(encoding="utf-8").splitlines() == ["--mock", "--sim"]


def test_gnome_wrapper_focuses_loading_window_and_reuses_its_browser(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    wrapper = repo_root / "scripts/launch-golf-one-gnome.sh"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "calls"

    xdotool = fake_bin / "xdotool"
    xdotool.write_text(
        "#!/bin/sh\n"
        'printf "xdotool %s\\n" "$*" >> "$GOLF_ONE_TEST_CALLS"\n'
        'if [ "$1" = search ]; then printf "4242\\n"; fi\n',
        encoding="utf-8",
    )
    xdotool.chmod(0o755)

    netcat = fake_bin / "nc"
    netcat.write_text(
        '#!/bin/sh\nprintf "GET /ready?t=1 HTTP/1.1\\r\\nHost: localhost\\r\\n\\r\\n"\n',
        encoding="utf-8",
    )
    netcat.chmod(0o755)

    curl = fake_bin / "curl"
    curl.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    curl.chmod(0o755)

    browser = tmp_path / "browser"
    browser.write_text(
        "#!/bin/sh\n"
        'printf "browser-url=%s\\n" "$1" >> "$GOLF_ONE_TEST_CALLS"\n'
        'printf "ozone=%s\\n" "$GOLF_ONE_OZONE_PLATFORM" '
        '>> "$GOLF_ONE_TEST_CALLS"\n'
        'printf "scale=%s\\n" "$GOLF_ONE_FORCE_DEVICE_SCALE_FACTOR" '
        '>> "$GOLF_ONE_TEST_CALLS"\n'
        "exec sleep 10\n",
        encoding="utf-8",
    )
    browser.chmod(0o755)

    launcher = tmp_path / "launcher"
    launcher.write_text(
        "#!/bin/sh\n"
        'printf "browser-owned=%s\\n" "$GOLF_ONE_BROWSER_ALREADY_RUNNING" '
        '>> "$GOLF_ONE_TEST_CALLS"\n'
        'printf "kiosk-url=%s\\n" "$GOLF_ONE_KIOSK_URL" '
        '>> "$GOLF_ONE_TEST_CALLS"\n'
        'printf "launcher-args=%s\\n" "$*" >> "$GOLF_ONE_TEST_CALLS"\n'
        "sleep 0.2\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    kiosk_url = "http://localhost:9876/"
    env = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "GOLF_ONE_BROWSER_SCRIPT": str(browser),
        "GOLF_ONE_LAUNCH_SCRIPT": str(launcher),
        "GOLF_ONE_KIOSK_URL": kiosk_url,
        "GOLF_ONE_TEST_CALLS": str(calls),
        "GOLF_ONE_GNOME_FOCUS_DELAY": "0",
        "GOLF_ONE_GNOME_MONITOR_DELAY": "0",
        "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
        "XDG_RUNTIME_DIR": str(runtime),
        "XDG_SESSION_TYPE": "x11",
        "DISPLAY": ":99",
    }
    result = subprocess.run(
        ["bash", str(wrapper), "--mock", "--sim"],
        check=False,
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
    )

    assert result.returncode == 0
    recorded = calls.read_text(encoding="utf-8")
    assert f"browser-url=file://{repo_root}/scripts/setup/kiosk-loading.html#{kiosk_url}" in recorded
    assert "ozone=x11" in recorded
    assert "scale=1" in recorded
    assert "browser-owned=1" in recorded
    assert f"kiosk-url={kiosk_url}" in recorded
    assert "launcher-args=--mock --sim" in recorded
    assert "xdotool search --onlyvisible --class GolfOneKiosk" in recorded
    assert "xdotool key --clearmodifiers Escape" in recorded
    assert "xdotool windowactivate --sync 4242" in recorded
    assert "xdotool windowfocus 4242" in recorded
    assert "Branded loading page painted" in result.stdout
    assert not (runtime / "golf-one-gnome-loading-page.ready").exists()


def test_gnome_session_installer_is_unprivileged_idempotent_and_backs_up(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    installer = repo_root / "scripts/setup/install-golf-one-gnome-session.sh"
    install_home = tmp_path / "home"
    autostart = install_home / ".config/autostart/GolfOne.desktop"
    application = install_home / ".local/share/applications/GolfOne.desktop"
    desktop = install_home / "Desktop/GolfOne.desktop"
    originals = {
        autostart: "old-autostart",
        application: "old-application",
        desktop: "old-desktop",
    }
    for path, content in originals.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    env = os.environ | {
        "HOME": str(install_home),
        "GOLF_ONE_DESKTOP_DIR": str(install_home / "Desktop"),
    }
    first = subprocess.run(
        ["bash", str(installer)],
        check=False,
        env=env,
        text=True,
        capture_output=True,
    )
    assert first.returncode == 0, first.stderr

    assert "launch-golf-one-gnome.sh" in autostart.read_text(encoding="utf-8")
    for path in (application, desktop):
        rendered = path.read_text(encoding="utf-8")
        assert f"Exec={repo_root}/scripts/launch-golf-one.sh" in rendered
        assert "@GOLF_ONE_PROJECT_DIR@" not in rendered

    backup_root = install_home / ".config/golf-one/backups"
    first_backups = list(backup_root.glob("gnome-session-*"))
    assert len(first_backups) == 1
    for path, content in originals.items():
        backup = first_backups[0] / path.relative_to(install_home)
        assert backup.read_text(encoding="utf-8") == content

    first_render = {path: path.read_bytes() for path in originals}
    second = subprocess.run(
        ["bash", str(installer)],
        check=False,
        env=env,
        text=True,
        capture_output=True,
    )
    assert second.returncode == 0, second.stderr
    assert {path: path.read_bytes() for path in originals} == first_render
    assert len(list(backup_root.glob("gnome-session-*"))) == 2

    source = installer.read_text(encoding="utf-8").lower()
    assert "sudo" not in source
    assert "lightdm" not in source
    assert "labwc" not in source


def test_session_installer_preserves_rotation_and_installs_recovery_launcher():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "scripts/setup/install-golf-one-session.sh").read_text(
        encoding="utf-8"
    )
    autostart = (repo_root / "scripts/setup/labwc-autostart").read_text(encoding="utf-8")

    assert 'cp "$LABWC_DIR/autostart" "$BACKUP_DIR/labwc-autostart.$STAMP"' in installer
    assert 'cp "$LABWC_DIR/rc.xml" "$BACKUP_DIR/labwc-rc.$STAMP.xml"' in installer
    assert 'install -m 0644 "$AUTOSTART_TEMP" "$LABWC_DIR/autostart"' in installer
    assert 'install -m 0644 "$SCRIPT_DIR/labwc-rc.xml" "$LABWC_DIR/rc.xml"' in installer
    assert 'install -m 0755 "$DESKTOP_TEMP"' in installer
    assert "/sys/class/drm/card*-DSI-*/status" in autostart
    assert '--output "$DISPLAY_OUTPUT"' in autostart
    assert '--transform "${GOLF_ONE_DISPLAY_TRANSFORM:-90}"' in autostart
    assert "@GOLF_ONE_PROJECT_DIR@" in autostart
    assert "./scripts/launch-golf-one.sh" in autostart
    assert "--mock --sim" not in autostart


def test_session_installer_disables_raspberry_pi_autotouch_rewriter():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "scripts/setup/install-golf-one-session.sh").read_text(
        encoding="utf-8"
    )
    override = (repo_root / "scripts/setup/autotouch.desktop").read_text(encoding="utf-8")

    assert 'AUTOSTART_DIR="$HOME/.config/autostart"' in installer
    assert (
        'install -m 0644 "$SCRIPT_DIR/autotouch.desktop" "$AUTOSTART_DIR/autotouch.desktop"'
    ) in installer
    assert "Hidden=true" in override


def test_appliance_session_does_not_create_the_pi_desktop_during_boot():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "scripts/setup/install-golf-one-appliance-session.sh").read_text(
        encoding="utf-8"
    )
    session_entry = (repo_root / "scripts/setup/golf-one-wayland.desktop").read_text(
        encoding="utf-8"
    )
    compositor = (repo_root / "scripts/start-appliance-session-compositor.sh").read_text(
        encoding="utf-8"
    )
    session = (repo_root / "scripts/run-appliance-session.sh").read_text(encoding="utf-8")
    loading_page = (repo_root / "scripts/setup/kiosk-loading.html").read_text(encoding="utf-8")
    cover = repo_root / "scripts/setup/session-cover.png"

    assert "/usr/share/wayland-sessions/golf-one.desktop" in installer
    assert "Goodix Capacitive TouchScreen" in installer
    assert "0 -1 1 1 0 0" in installer
    assert re.search(r"(?m)^Exec=/(?:home|usr/local)/.+$", session_entry)
    assert 'SCRIPT_PATH="$(readlink -f "$0"' in compositor
    assert '--config-dir "$SESSION_CONFIG_DIR"' in compositor
    assert "--merge-config" not in compositor

    # Only calls in main() establish runtime order. Looking at the whole source
    # would accidentally compare function-definition order instead.
    main_body = _bash_function_body(session, "main")
    cover_ready = main_body.index("show_session_cover")
    stale_function = next(
        name
        for name in ("stop_stale_profile_browsers", "stop_stale_kiosk_browser")
        if name in main_body
    )
    stale_browser_stopped = main_body.index(stale_function)
    paint_listener = main_body.index("start_loading_page_ready_server")
    loading_browser = main_body.index('open-kiosk-browser.sh" "$BOOT_PAGE_URL"')
    dashboard_started = main_body.index('launch-golf-one.sh"')
    renderer_ready = main_body.index("wait_for_browser_renderer", dashboard_started)
    paint_waiter = main_body.index("wait_for_loading_page_ready", renderer_ready)
    app_waiter = main_body.index("wait_for_owned_app", paint_waiter)
    exit_marker_check = main_body.index("if desktop_exit_is_valid", app_waiter)
    desktop_started = main_body.index("start_raspberry_pi_desktop", exit_marker_check)
    cover_dismissed = main_body.index("dismiss_session_cover", desktop_started)
    assert (
        cover_ready
        < stale_browser_stopped
        < paint_listener
        < loading_browser
        < dashboard_started
        < renderer_ready
        < paint_waiter
        < app_waiter
        < exit_marker_check
        < desktop_started
        < cover_dismissed
    )
    assert main_body.count("start_raspberry_pi_desktop") == 1
    assert 'GOLF_ONE_DESKTOP_EXIT_FILE="$DESKTOP_REQUEST_FILE"' in main_body
    marker_validator = _bash_function_body(session, "desktop_exit_is_valid")
    assert '[ ! -L "$DESKTOP_REQUEST_FILE" ]' in marker_validator
    assert '"$(cat "$DESKTOP_REQUEST_FILE"' in marker_validator
    assert '[ "$marker_mode" = "600" ]' in marker_validator
    assert '[ "$marker_owner" = "$(id -u)" ]' in marker_validator
    app_monitor = _bash_function_body(session, "wait_for_owned_app")
    assert 'browser_pid_uses_profile "$BOOT_BROWSER_PID"' in app_monitor
    assert "desktop_exit_is_valid" in app_monitor
    assert "show_session_cover" in app_monitor
    assert 'stop_exact_pid "$APP_PID"' in app_monitor
    assert "/usr/bin/setsid /usr/bin/swaybg" in session
    assert "/usr/bin/swaylock" not in session
    assert "command -v swaybg" in installer
    assert "/usr/bin/lxsession-xdg-autostart" in session
    assert "/usr/bin/pcmanfm-pi" in session
    assert "/usr/bin/wf-panel-pi" in session
    assert "http://localhost:8080/" in session
    assert "?autolaunch=1" not in session

    assert "Golf One is starting" in loading_page
    assert "http://localhost:8080/" in loading_page
    assert "http://127.0.0.1:38917/ready" in loading_page
    assert loading_page.count("window.requestAnimationFrame") >= 2
    assert "OpenGolfSim" not in loading_page

    header = cover.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", header[16:24]) == (1920, 720)


def test_appliance_background_is_fail_closed_and_tracks_the_exact_swaybg_process():
    repo_root = Path(__file__).resolve().parents[1]
    session = (repo_root / "scripts/run-appliance-session.sh").read_text(encoding="utf-8")
    show_cover = _bash_function_body(session, "show_session_cover")
    dismiss_cover = _bash_function_body(session, "dismiss_session_cover")
    main_body = _bash_function_body(session, "main")

    for prerequisite in (
        r"if \[ ! -x /usr/bin/swaybg \]; then",
        r'if \[ ! -f "\$COVER_IMAGE" \]; then',
        r'if \[ ! -f "\$COVER_VERIFIER" \]; then',
    ):
        guard = re.search(
            rf"(?ms){prerequisite}(?P<body>.*?)^[ \t]*fi[ \t]*$",
            show_cover,
        )
        assert guard is not None
        assert "return 1" in guard.group("body")

    # Isolate and track the exact branded background instead of relying on a
    # global process lookup or a session lock that blocks Chromium painting.
    assert "pgrep" not in show_cover
    assert "swaylock" not in show_cover
    assert "/usr/bin/setsid /usr/bin/swaybg" in show_cover
    assert '--output "$DISPLAY_OUTPUT"' in show_cover
    assert '--image "$COVER_IMAGE"' in show_cover
    assert "--mode fill" in show_cover
    assert '/usr/bin/grim -o "$DISPLAY_OUTPUT"' in show_cover
    assert '"$COVER_VERIFIER"' in show_cover
    pid_capture = re.search(r'(?P<variable>COVER_PID|cover_pid)=(?:"\$!"|\$!)', show_cover)
    assert pid_capture is not None
    pgid_capture = show_cover.index('candidate_pgid="$(ps -o pgid=')
    pid_write = show_cover.index('"$COVER_PID" "$COVER_PGID" >"$COVER_PID_FILE"')
    pixel_proof = show_cover.index('/usr/bin/grim -o "$DISPLAY_OUTPUT"')
    assert pid_capture.start() < pgid_capture < pid_write < pixel_proof
    assert 'if [ "$candidate_pgid" = "$COVER_PID" ]; then' in show_cover
    assert 'COVER_PGID="$candidate_pgid"' in show_cover
    assert 'stop_process_group "$COVER_PGID"' in show_cover
    assert "return 1" in show_cover

    # A missing or unready cover must stop startup before desktop content can
    # be exposed. Recovery remains possible from SSH.
    fail_closed = re.search(
        r"(?ms)if ! show_session_cover; then(?P<body>.*?)^[ \t]*fi[ \t]*$",
        main_body,
    )
    assert fail_closed is not None
    assert "exit 1" in fail_closed.group("body") or "while :;" in fail_closed.group("body")

    assert 'process_group_exists "$COVER_PGID"' in dismiss_cover
    assert (
        'stop_process_group "$COVER_PGID"' in dismiss_cover
        or 'stop_exact_pid "$COVER_PID"' in dismiss_cover
    )
    assert "pgrep" not in dismiss_cover
    assert "pkill" not in dismiss_cover
    assert "killall" not in dismiss_cover


def test_appliance_removes_only_stale_profile_processes_before_opening_browser():
    repo_root = Path(__file__).resolve().parents[1]
    session = (repo_root / "scripts/run-appliance-session.sh").read_text(encoding="utf-8")
    main_body = _bash_function_body(session, "main")
    cleanup_name = next(
        name
        for name in ("stop_stale_profile_browsers", "stop_stale_kiosk_browser")
        if re.search(rf"(?m)^{name}\(\) \{{", session)
    )
    cleanup = _bash_function_body(session, cleanup_name)

    chromium_pattern = "chromium.*--user-data-dir=$KIOSK_PROFILE_DIR"
    chrome_pattern = "chrome.*--user-data-dir=$KIOSK_PROFILE_DIR"

    if "find_profile_browser_pids" in cleanup:
        finder = _bash_function_body(session, "find_profile_browser_pids")
        assert "for cmdline in /proc/[0-9]*/cmdline" in finder
        assert "chromium*|chrome*" in finder
        assert "cmdline_text=\"$(tr '\\0' ' '" in finder
        assert '*" --user-data-dir=$KIOSK_PROFILE_DIR "*)' in finder
        assert '*" $required_arg "*)' in finder
        assert "stop_exact_pid" in cleanup
        assert cleanup.count("find_profile_browser_pids") >= 2
    else:
        assert f'pkill -f "{chromium_pattern}"' in cleanup
        assert f'pkill -f "{chrome_pattern}"' in cleanup
        assert f'pgrep -f "{chromium_pattern}"' in cleanup
        assert f'pgrep -f "{chrome_pattern}"' in cleanup

    assert "pkill -x chromium" not in cleanup
    assert "pkill -x chrome" not in cleanup
    assert "killall" not in cleanup

    cleanup_call = main_body.index(cleanup_name)
    browser_open = main_body.index('open-kiosk-browser.sh" "$BOOT_PAGE_URL"')
    assert cleanup_call < browser_open
    cleanup_guard = re.search(
        rf"(?ms)if ! {cleanup_name}; then(?P<body>.*?)^[ \t]*fi[ \t]*$",
        main_body,
    )
    assert cleanup_guard is not None
    assert "exit 1" in cleanup_guard.group("body") or "while :;" in cleanup_guard.group("body")


def test_appliance_session_has_one_chromium_owner_and_one_profile():
    repo_root = Path(__file__).resolve().parents[1]
    session = (repo_root / "scripts/run-appliance-session.sh").read_text(encoding="utf-8")
    launcher = (repo_root / "scripts/launch-golf-one.sh").read_text(encoding="utf-8")
    start_kiosk = (repo_root / "scripts/start-kiosk.sh").read_text(encoding="utf-8")
    browser = (repo_root / "scripts/open-kiosk-browser.sh").read_text(encoding="utf-8")
    main_body = _bash_function_body(session, "main")

    profile_defaults = []
    for source, variable in (
        (session, "KIOSK_PROFILE_DIR"),
        (start_kiosk, "KIOSK_PROFILE_DIR"),
        (browser, "PROFILE_DIR"),
    ):
        profile = re.search(
            rf'(?m)^{variable}="\$\{{GOLF_ONE_BROWSER_PROFILE_DIR:-(?P<path>[^}}]+)\}}"$',
            source,
        )
        assert profile is not None
        profile_defaults.append(profile.group("path"))
    assert profile_defaults == ["$HOME/.config/golf-one-kiosk/chromium"] * 3

    # The appliance session opens the loading page once. The launcher and
    # start-kiosk server path inherit the explicit ownership flag and therefore
    # cannot race another Chromium ProcessSingleton for the same profile.
    assert main_body.count('open-kiosk-browser.sh"') == 1
    owner_flag = main_body.index("GOLF_ONE_BROWSER_ALREADY_RUNNING=1")
    launcher_call = main_body.index('launch-golf-one.sh"')
    assert owner_flag < launcher_call

    launcher_open = _bash_function_body(launcher, "open_kiosk_browser")
    launcher_guard = launcher_open.index('if [ "$BROWSER_ALREADY_RUNNING" = "1" ]')
    launcher_exec = launcher_open.index('exec "$SCRIPT_DIR/open-kiosk-browser.sh"')
    assert launcher_guard < launcher_exec
    assert "return 0" in launcher_open[launcher_guard:launcher_exec]

    reuse_branch = start_kiosk.index('if [ "${GOLF_ONE_BROWSER_ALREADY_RUNNING:-0}" = "1" ]; then')
    branch_else = start_kiosk.index("\nelse", reuse_branch)
    browser_call = start_kiosk.index('"$SCRIPT_DIR/open-kiosk-browser.sh"', branch_else)
    branch_end = start_kiosk.index("\nfi", browser_call)
    assert reuse_branch < branch_else < browser_call < branch_end


def test_appliance_installer_edits_and_verifies_effective_lightdm_configuration():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "scripts/setup/install-golf-one-appliance-session.sh").read_text(
        encoding="utf-8"
    )

    assert 'LIGHTDM_MAIN="/etc/lightdm/lightdm.conf"' in installer
    assert "golf-one-lightdm.conf" not in installer
    assert 'LEGACY_LIGHTDM_TARGET="/etc/lightdm/lightdm.conf.d/' in installer
    assert 'rm -f "$LEGACY_LIGHTDM_TARGET"' in installer
    assert not re.search(
        r'install\b[^\n]*"\$LEGACY_LIGHTDM_TARGET"',
        installer,
    )
    assert 'cp -a "$LIGHTDM_MAIN" "$BACKUP_DIR/lightdm.conf"' in installer
    assert "autologin-session=golf-one" in installer

    write_main = re.search(
        r'(?ms)install\b.{0,240}"\$LIGHTDM_TEMP"[ \t\\\n]+"\$LIGHTDM_MAIN"',
        installer,
    )
    assert write_main is not None
    effective_check = installer.index("--show-config", write_main.end())
    verification = installer[effective_check:]
    assert 'if ! EFFECTIVE_LIGHTDM="$("$LIGHTDM_BIN" --show-config 2>&1)"; then' in installer
    assert "autologin-session=golf-one" in verification
    assert "exit 1" in verification
    assert re.search(
        r'(?:cp -a|install -m 0644) "\$BACKUP_DIR/lightdm\.conf" "\$LIGHTDM_MAIN"',
        verification,
    )


def test_appliance_installer_disables_autotouch_for_the_target_user():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "scripts/setup/install-golf-one-appliance-session.sh").read_text(
        encoding="utf-8"
    )
    override = (repo_root / "scripts/setup/autotouch.desktop").read_text(encoding="utf-8")

    assert "Hidden=true" in override
    assert 'AUTOSTART_DIR="$TARGET_HOME/.config/autostart"' in installer
    assert re.search(
        r'(?ms)install -d\b.{0,180}-o "\$TARGET_USER".{0,180}"\$AUTOSTART_DIR"',
        installer,
    )
    assert re.search(
        r'(?ms)install\b.{0,220}-o "\$TARGET_USER".{0,220}'
        r'"\$SCRIPT_DIR/autotouch\.desktop".{0,120}"\$AUTOTOUCH_TARGET"',
        installer,
    )


def test_appliance_installer_owns_the_writable_golf_one_config_directory():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "scripts/setup/install-golf-one-appliance-session.sh").read_text(
        encoding="utf-8"
    )

    assert 'GOLF_ONE_CONFIG_DIR="$TARGET_HOME/.config/golf-one"' in installer
    assert 'SESSION_CONFIG_DIR="$GOLF_ONE_CONFIG_DIR/labwc"' in installer
    assert re.search(
        r'(?ms)install -d\b.{0,180}-o "\$TARGET_USER".{0,180}'
        r'"\$GOLF_ONE_CONFIG_DIR".{0,120}"\$SESSION_CONFIG_DIR"',
        installer,
    )


def test_appliance_session_entry_cannot_point_at_a_different_user_or_checkout():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "scripts/setup/install-golf-one-appliance-session.sh").read_text(
        encoding="utf-8"
    )
    session_entry = (repo_root / "scripts/setup/golf-one-wayland.desktop").read_text(
        encoding="utf-8"
    )
    fixed_project = "/home/openflight/golf-one-openflight"
    exec_match = re.search(r"(?m)^Exec=(?P<target>/\S+)$", session_entry)
    assert exec_match is not None
    exec_target = exec_match.group("target")

    if exec_target == f"{fixed_project}/scripts/start-appliance-session-compositor.sh":
        assert 'TARGET_USER="openflight"' in installer
        assert "GOLF_ONE_APPLIANCE_USER" not in installer
        assert "SUDO_USER" not in installer
        assert f'SUPPORTED_PROJECT_DIR="{fixed_project}"' in installer
        location_guard = re.search(
            r'(?ms)if \[ "\$PROJECT_DIR" != "\$SUPPORTED_PROJECT_DIR" \]; then'
            r"(?P<body>.*?)^[ \t]*fi[ \t]*$",
            installer,
        )
        assert location_guard is not None
        assert "exit 1" in location_guard.group("body")
    elif exec_target.startswith("/usr/local/"):
        # A system-owned entry is portable across home directories only when
        # the installer creates that exact target and links it to the checkout
        # whose adjacent appliance-session script it will execute.
        assert f'SESSION_COMMAND="{exec_target}"' in installer
        assert (
            'ln -s "$PROJECT_DIR/scripts/start-appliance-session-compositor.sh" "$SESSION_COMMAND"'
        ) in installer
    else:
        # A portable installer must render both the selected user and checkout
        # into the session entry before installing it.
        assert "@GOLF_ONE_PROJECT_DIR@" in session_entry
        assert "@GOLF_ONE_USER@" in session_entry
        assert "SESSION_ENTRY_TEMP" in installer
        assert "GOLF_ONE_PROJECT_DIR" in installer
        assert "GOLF_ONE_USER" in installer
        assert '"$SESSION_ENTRY_TEMP" "$WAYLAND_TARGET"' in installer


def test_appliance_installer_generates_one_touch_rule_without_output_mapping():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "scripts/setup/install-golf-one-appliance-session.sh").read_text(
        encoding="utf-8"
    )

    # Remove inherited Goodix rules, including Raspberry Pi OS device names
    # prefixed with an I2C address, before adding one generic touch category.
    assert 'contains(@deviceName, "Goodix Capacitive TouchScreen")' in installer
    assert (
        "-d '/labwc:openbox_config/labwc:libinput/labwc:device[@category=\"touch\"]'"
    ) in installer
    assert 'contains(@category, "Goodix Capacitive TouchScreen")' in installer
    assert installer.count("-n category -v 'touch'") == 1
    assert installer.count("-n calibrationMatrix -v '0 -1 1 1 0 0'") == 1
    assert "-n mapToOutput" not in installer
    assert "TOUCH_DEVICE_COUNT" in installer
    assert "LEGACY_GOODIX_TOUCH_COUNT" in installer
    assert "TOUCH_MAP_COUNT" in installer
    assert "TOUCH_MATRIX" in installer
    assert '[ "$TOUCH_DEVICE_COUNT" != "1" ]' in installer
    assert '[ "$LEGACY_GOODIX_TOUCH_COUNT" != "0" ]' in installer
    assert '[ "$TOUCH_MAP_COUNT" != "0" ]' in installer
    assert '[ "$TOUCH_MATRIX" != "0 -1 1 1 0 0" ]' in installer


def test_waveshare_touch_calibration_cancels_reported_corner_rotation():
    repo_root = Path(__file__).resolve().parents[1]
    config_path = repo_root / "scripts/setup/labwc-rc.xml"
    root = ET.parse(config_path).getroot()
    namespace = {"labwc": "http://openbox.org/3.4/rc"}
    calibration = root.find(
        "./labwc:libinput/labwc:device"
        "[@category='touch']/"
        "labwc:calibrationMatrix",
        namespace,
    )
    touch = root.find(
        "./labwc:touch[@deviceName='Goodix Capacitive TouchScreen']",
        namespace,
    )

    assert touch is None
    assert calibration is not None
    matrix = tuple(float(value) for value in calibration.text.split())
    assert matrix == (0, -1, 1, 1, 0, 0)

    corners = {
        "top-left": (0, 0),
        "bottom-left": (0, 1),
        "bottom-right": (1, 1),
        "top-right": (1, 0),
    }
    observed_before = {name: _rotate_counterclockwise(point) for name, point in corners.items()}
    observed_after = {
        name: _rotate_counterclockwise(_apply_calibration(matrix, point))
        for name, point in corners.items()
    }

    assert observed_before == {
        "top-left": (0, 1),
        "bottom-left": (1, 1),
        "bottom-right": (1, 0),
        "top-right": (0, 0),
    }
    assert observed_after == corners


def test_simulator_extension_exposes_persistent_display_settings():
    repo_root = Path(__file__).resolve().parents[1]
    content = (repo_root / "browser-extension/content.js").read_text(encoding="utf-8")
    background = (repo_root / "browser-extension/background.js").read_text(encoding="utf-8")

    assert "Display settings" in content
    assert "Golf One Settings" in content
    assert "golf-one-settings" in content
    assert "http://127.0.0.1:8080/?settings=1" in content
    assert "golf-one-status" in background
    assert "{ type: 'golf-one-shutdown', pin: exitPin.value }" in content
    assert "JSON.stringify({ pin: message.pin })" in background


def test_simulator_extension_relays_local_shots_into_the_fuse_game():
    repo_root = Path(__file__).resolve().parents[1]
    content = (repo_root / "browser-extension/content.js").read_text(encoding="utf-8")
    background = (repo_root / "browser-extension/background.js").read_text(encoding="utf-8")

    assert 'iframe[title="fuse"]' in content
    assert "event.source !== gameFrame.contentWindow" in content
    assert "golf-one-game-session" in content
    assert "golf-one-game-poll" in content
    assert "golf-one-game-ack" in content
    assert "gameFrame.contentWindow.postMessage" in content
    assert "new URL(gameFrame.src).origin" in content
    assert "event.data.type === 'player'" in content
    assert "event.data.type === 'result'" in content
    assert "METERS_TO_YARDS = 1.0936133" in content
    assert "carryMeters * METERS_TO_YARDS" in content
    assert "/api/opengolfsim/browser/session" in background
    assert "/api/opengolfsim/browser/poll" in background
    assert "/api/opengolfsim/browser/ack" in background
    assert "'X-Golf-One-Extension': 'browser-relay-v1'" in background
    assert "sender?.origin" in background


def test_simulator_extension_manifest_rolls_out_browser_relay_worker():
    repo_root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (repo_root / "browser-extension/manifest.json").read_text(encoding="utf-8")
    )

    version = tuple(int(part) for part in manifest["version"].split("."))
    assert version >= (1, 2, 0)
    matches = manifest["content_scripts"][0]["matches"]
    assert "http://127.0.0.1:8080/offline-simulator*" in matches
    assert "http://localhost:8080/offline-simulator*" in matches


def test_simulator_extension_accepts_only_official_or_loopback_game_pages():
    repo_root = Path(__file__).resolve().parents[1]
    background = (repo_root / "browser-extension/background.js").read_text(encoding="utf-8")

    assert "isSimulatorSender" in background
    assert "https://app.opengolfsim.com" in background
    assert "http://127.0.0.1:8080" in background
    assert "http://localhost:8080" in background


def test_simulator_extension_defaults_to_full_width_with_recoverable_controls():
    repo_root = Path(__file__).resolve().parents[1]
    content = (repo_root / "browser-extension/content.js").read_text(encoding="utf-8")

    assert "OpenGolfSim controls" in content
    assert "setProperty('margin-left', '0px', 'important')" in content
    assert "restoreOpenGolfSimLayout" in content


def test_simulator_extension_closes_stale_spa_games_and_recovers_visual_test():
    repo_root = Path(__file__).resolve().parents[1]
    content = (repo_root / "browser-extension/content.js").read_text(encoding="utf-8")

    assert "if (gameFrame && !nextFrame)" in content
    assert "closeGameSession('iframe-removed')" in content
    assert "DIRECT_RANGE_RECOVERY_MS" in content
    assert "inFlightShot = null" in content
    assert "window.location.pathname.startsWith('/fuse/examples/range')" in content
    assert "scheduleGameSessionRetry" in content
    assert "GAME_SESSION_RETRY_MAX_MS" in content


def test_offline_fuse_installer_is_pinned_and_keeps_third_party_code_out_of_repo():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "scripts/setup/install-offline-fuse-range.sh").read_text(
        encoding="utf-8"
    )

    assert "6f10092c4444a538dd869d495eb2cb45697a5fb5" in installer
    assert "https://github.com/OpenGolfSim/fuse.git" in installer
    assert "GOLF_ONE_OFFLINE_FUSE_INSTALL_ROOT" in installer
    assert "LICENSE.md" in installer
    assert "password" not in installer.lower()


def test_offline_fuse_installer_builds_guarded_board_specific_variant():
    repo_root = Path(__file__).resolve().parents[1]
    installer = (repo_root / "scripts/setup/install-offline-fuse-range.sh").read_text(
        encoding="utf-8"
    )

    assert 'FUSE_PROFILE="${GOLF_ONE_FUSE_PROFILE:-auto}"' in installer
    assert (
        'DEVICE_MODEL_PATH="${GOLF_ONE_DEVICE_MODEL_PATH:-/proc/device-tree/model}"'
        in installer
    )
    assert 'FUSE_PROFILE="pi-balanced"' in installer
    assert 'FUSE_PROFILE="full"' in installer
    assert 'FUSE_VARIANT="range-explicit-webgl-v1"' in installer
    assert 'FUSE_VARIANT="range-explicit-webgl-anisotropy4-v3"' in installer
    assert 'VERSION_ID="${FUSE_COMMIT}-${FUSE_VARIANT}"' in installer
    assert 'VERSION_DIR="$INSTALL_ROOT/$VERSION_ID"' in installer
    assert 'FUSE_PATCH="$SCRIPT_DIR/patches/fuse-$VERSION_ID.patch"' in installer
    assert (
        'ACTUAL_FUSE_COMMIT="$(git -C "$SOURCE_DIR" rev-parse HEAD)"' in installer
    )
    assert 'if [ "$ACTUAL_FUSE_COMMIT" != "$FUSE_COMMIT" ]; then' in installer
    assert (
        'git -C "$SOURCE_DIR" apply --unidiff-zero --check "$FUSE_PATCH"'
        in installer
    )
    assert 'git -C "$SOURCE_DIR" apply --unidiff-zero "$FUSE_PATCH"' in installer
    assert (
        'printf \'%s\\n\' "$FUSE_VARIANT" > "$STAGING_DIR/BUILD_VARIANT"'
        in installer
    )
    assert (
        'printf \'%s\\n\' "$PATCH_SHA256" > "$STAGING_DIR/SOURCE_PATCH_SHA256"'
        in installer
    )
    assert 'PREVIOUS_LINK="$INSTALL_ROOT/previous"' in installer


def test_offline_fuse_renderer_patch_changes_only_range_backend():
    repo_root = Path(__file__).resolve().parents[1]
    patch = (
        repo_root / "scripts/setup/patches/"
        "fuse-6f10092c4444a538dd869d495eb2cb45697a5fb5-range-explicit-webgl-v1.patch"
    ).read_text(encoding="utf-8")

    removed_lines = [
        line[1:]
        for line in patch.splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]
    added_lines = [
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]

    assert "diff --git a/examples/range/range.ts b/examples/range/range.ts" in patch
    assert removed_lines == ["    renderMode: 'webgpu',"]
    assert added_lines == ["    renderMode: 'webgl',"]


def test_pi_balanced_fuse_patch_keeps_msaa_and_caps_only_range_grass_textures():
    repo_root = Path(__file__).resolve().parents[1]
    patch = (
        repo_root / "scripts/setup/patches/"
        "fuse-6f10092c4444a538dd869d495eb2cb45697a5fb5-"
        "range-explicit-webgl-anisotropy4-v3.patch"
    ).read_text(encoding="utf-8")

    assert "diff --git a/examples/range/range.ts b/examples/range/range.ts" in patch
    assert "antialias: true," in patch
    assert "antialias: false," not in patch
    assert "-    renderMode: 'webgpu'," in patch
    assert "+    renderMode: 'webgl'," in patch
    assert patch.count("+  grass") == 2
    assert (
        patch.count("Math.min(gameContext.renderer?.getMaxAnisotropy() || 1, 4)")
        == 2
    )
    assert "src/renderer.ts" not in patch
    assert "src/lights.ts" not in patch


def test_offline_fuse_installer_preserves_active_runtime_for_rollback(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    installer = repo_root / "scripts/setup/install-offline-fuse-range.sh"
    patch = (
        repo_root / "scripts/setup/patches/"
        "fuse-6f10092c4444a538dd869d495eb2cb45697a5fb5-range-explicit-webgl-v1.patch"
    )
    commit = "6f10092c4444a538dd869d495eb2cb45697a5fb5"
    variant_name = f"{commit}-range-explicit-webgl-v1"
    install_root = tmp_path / "fuse"
    baseline = install_root / commit
    variant = install_root / variant_name

    for runtime in (baseline, variant):
        (runtime / "examples/range").mkdir(parents=True)
        (runtime / "examples/range/index.html").write_text(
            f"<!doctype html><title>{runtime.name}</title>",
            encoding="utf-8",
        )
    (baseline / "rollback-marker").write_text("keep me", encoding="utf-8")
    (variant / "SOURCE_COMMIT").write_text(f"{commit}\n", encoding="utf-8")
    (variant / "BUILD_VARIANT").write_text(
        "range-explicit-webgl-v1\n",
        encoding="utf-8",
    )
    (variant / "SOURCE_PATCH_SHA256").write_text(
        f"{hashlib.sha256(patch.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
    )
    (install_root / "current").symlink_to(baseline, target_is_directory=True)

    result = subprocess.run(
        ["bash", str(installer)],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GOLF_ONE_OFFLINE_FUSE_INSTALL_ROOT": str(install_root),
        },
    )

    assert (install_root / "current").resolve() == variant.resolve()
    assert (install_root / "previous").resolve() == baseline.resolve()
    assert (baseline / "rollback-marker").read_text(encoding="utf-8") == "keep me"
    assert "Build variant: range-explicit-webgl-v1" in result.stdout
    assert f"Rollback runtime: {install_root / 'previous'}" in result.stdout
