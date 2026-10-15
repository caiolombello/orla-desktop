"""Run the CC audio integration with private KWin, D-Bus, XDG and PipeWire.

Needs Linux pidfds, KWin virtual backend, PipeWire, pactl, PySide6 and KDE QML.
Does not install an applet, change host audio, or send input to the user's seat.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", required=True, help="new absolute ASCII path without spaces, e.g. /tmp/orla-cc-audio-1")
    parser.add_argument("--style", choices=("Fusion", "org.kde.desktop"), default="Fusion")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    area = Path(args.area)
    assert re.fullmatch(r"/[A-Za-z0-9_./-]+", str(area)), "simple_ascii_area_path_required"
    assert area.is_absolute() and area.parent.resolve() == area.parent and not area.exists(), "new_absolute_area_required"
    assert not area.is_symlink() and len(os.fsencode(area / "run/pulse-native")) < 100, "short_owned_socket_path_required"
    assert hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"), "linux_pidfds_required"
    interpreter = Path("/usr/bin/python3").resolve()
    assert Path(sys.executable).resolve() == interpreter, "system_python_with_kde_runtime_required"
    for command in ("dbus-run-session", "kwin_wayland", "pipewire", "pactl"):
        assert shutil.which(command), "missing_dependency:" + command
    area.mkdir(mode=0o700)
    for directory in ("run", "config", "data", "cache", "empty"):
        (area / directory).mkdir(mode=0o700)

    def save(name, value):
        with (area / name).open("x") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, indent=2)
            stream.write("\n")

    files = sorted(path for root in (repo / "package", repo / "bar") for path in root.rglob("*")
                   if path.suffix in (".qml", ".js") or path.name == "qmldir")
    files += [repo / "tests/QmlHarness.qml", repo / "tests/SharedControlCenterBarHarness.qml"]
    files += sorted((repo / "tests/native").glob("*control_center_audio*"))
    pins = {str(path.relative_to(repo)): digest(path) for path in files if path.is_file()}
    save("SOURCE-PINS.json", pins)
    session = area / "session.py"
    session.write_bytes((repo / "tests/native/control_center_audio_session.py").read_bytes())
    session.chmod(0o500)
    applications = area / "data/applications"
    applications.mkdir(mode=0o700)
    applications.joinpath("org.orla.ModelProbe.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Orla isolated probe\nExec=" + str(interpreter) + "\n"
        "NoDisplay=true\nX-KDE-Wayland-Interfaces=org_kde_plasma_window_management\n")
    template = repo / "tests/native/control_center_audio.conf.in"
    config = template.read_text()
    assert config.count("SOCKET") == 1, "one_private_audio_socket_required"
    (area / "config/audio-server.conf").write_text(config.replace("SOCKET", str(area / "run/pulse-native")))
    (area / "config/pulse-client.conf").write_text(
        "autospawn = no\ndefault-server = unix:" + str(area / "run/pulse-native") + "\n")

    env = dict(os.environ)
    parent_bus = env.get("DBUS_SESSION_BUS_ADDRESS", "")
    for key in ("DBUS_SESSION_BUS_ADDRESS", "DBUS_SESSION_BUS_PID", "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE",
                "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "DISPLAY", "XAUTHORITY", "SESSION_MANAGER",
                "LD_LIBRARY_PATH", "LD_PRELOAD", "QML_IMPORT_PATH", "QML2_IMPORT_PATH",
                "PULSE_SERVER", "PULSE_CLIENTCONFIG", "PULSE_RUNTIME_PATH", "PULSE_STATE_PATH", "PULSE_COOKIE",
                "PIPEWIRE_REMOTE", "PIPEWIRE_RUNTIME_DIR", "PIPEWIRE_CONFIG_DIR", "PIPEWIRE_CONFIG_PREFIX",
                "PIPEWIRE_CONFIG_NAME", "PIPEWIRE_PROPS", "PIPEWIRE_MODULE_DIR", "SPA_PLUGIN_DIR", "SPA_SUPPORT_LIB"):
        env.pop(key, None)
    for key, directory in (("XDG_RUNTIME_DIR", "run"), ("XDG_CONFIG_HOME", "config"),
                           ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
        env[key] = str(area / directory)
    env.update(ORLA_PARENT_BUS=parent_bus, ORLA_NATIVE_REPO=str(repo),
               XDG_CONFIG_DIRS=str(area / "empty"), XDG_DATA_DIRS="/usr/share",
               DBUS_SYSTEM_BUS_ADDRESS="unix:path=" + str(area / "run/absent-system"),
               PIPEWIRE_RUNTIME_DIR=str(area / "run"), PIPEWIRE_REMOTE="orla-audio",
               PIPEWIRE_CONFIG_DIR=str(area / "config"), PULSE_SERVER="unix:" + str(area / "run/pulse-native"),
               PULSE_CLIENTCONFIG=str(area / "config/pulse-client.conf"),
               QML_DISK_CACHE_PATH=str(area / "cache/qml"),
               QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="", QT_QUICK_CONTROLS_STYLE=args.style,
               QT_QUICK_BACKEND="software", LIBGL_ALWAYS_SOFTWARE="true", PYTHONDONTWRITEBYTECODE="1")

    # Compare bytes/modes only; do not record personal configuration contents.
    def host_fingerprint():
        home = Path.home()
        paths = [home / ".config" / name for name in (
            "plasma-org.kde.plasma.desktop-appletsrc", "kglobalshortcutsrc", "kwinrc", "kscreenlockerrc")]
        paths += [home / ".local/bin/orla-launcher", home / ".local/bin/orla-launcherctl"]
        for plugin in ("org.caiodock.dock", "org.orla.bar"):
            root = home / ".local/share/plasma/plasmoids" / plugin
            if root.is_dir():
                paths += sorted(root.rglob("*"))
        snapshot = {}
        for path in paths:
            label = str(path.relative_to(home))
            try:
                info = path.lstat()
            except FileNotFoundError:
                snapshot[label] = {"kind": "absent"}
                continue
            item = {"mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid}
            if path.is_symlink():
                item.update(kind="symlink", targetDigest=hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest())
            elif path.is_file():
                item.update(kind="file", sha256=digest(path))
            else:
                item["kind"] = "directory"
            snapshot[label] = item
        return snapshot

    marker = b"XDG_RUNTIME_DIR=" + os.fsencode(area / "run")
    birth_tick = math.floor(time.clock_gettime(time.CLOCK_BOOTTIME) * os.sysconf("SC_CLK_TCK")) - 1

    def owned_fact(path):
        try:
            if path.stat().st_uid != os.getuid():
                return None
            fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
            tick = int(fields[19])
            if tick < birth_tick or fields[0] == "Z" or marker not in (path / "environ").read_bytes().split(b"\0"):
                return None
            return int(path.name), tick
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            return None

    def owned():
        return [value for path in Path("/proc").iterdir() if path.name.isdigit()
                and (value := owned_fact(path)) is not None]

    def stop_owned(sig):
        for pid, tick in owned():
            fd = None
            try:
                fd = os.pidfd_open(pid)
                if owned_fact(Path("/proc") / str(pid)) == (pid, tick):
                    signal.pidfd_send_signal(fd, sig)
            except ProcessLookupError:
                pass
            except BaseException as error:
                result["cleanupErrors"].append("signal_" + type(error).__name__)
            finally:
                if fd is not None:
                    os.close(fd)

    def wait_gone(seconds):
        until = time.monotonic() + seconds
        while owned() and time.monotonic() < until:
            time.sleep(0.05)
        return not owned()

    result = {"status": "PREPARING", "firstError": None, "cleanupErrors": [], "style": args.style,
              "inputToHost": False, "scope": "isolated Source protocol fixture, no installed-session/hardware claim"}
    process = None
    before = None
    try:
        before = host_fingerprint()
        save("HOST-BEFORE.json", before)
        command = ["dbus-run-session", "--", "kwin_wayland", "--virtual", "--width", "800", "--height", "600",
                   "--no-lockscreen", "--no-global-shortcuts", "--no-kactivities", "--socket", "orla-model",
                   "--exit-with-session", str(session)]
        with (area / "COMPOSITOR.stdout").open("x") as stdout, (area / "COMPOSITOR.stderr").open("x") as stderr:
            process = subprocess.Popen(command, env=env, stdout=stdout, stderr=stderr, start_new_session=True, umask=0o077)
            result["exitCode"] = process.wait(timeout=55)
    except BaseException as error:
        result["firstError"] = type(error).__name__
    finally:
        try:
            stop_owned(signal.SIGTERM)
            if not wait_gone(4):
                stop_owned(signal.SIGKILL)
            result["ownedProcessesGone"] = wait_gone(2)
            if process is not None:
                process.wait(timeout=2)
        except BaseException as error:
            result["cleanupErrors"].append("process_" + type(error).__name__)
        try:
            if result.get("ownedProcessesGone"):
                for name in ("COMPOSITOR.stdout", "COMPOSITOR.stderr", "AUDIO.stdout", "AUDIO.stderr"):
                    path = area / name
                    if path.exists():
                        assert path.stat().st_size <= 8 * 1024 * 1024, "log_size_bound"
                        path.write_text(path.read_text(errors="replace").replace(str(Path.home()), "<home>"))
                result["logsRedacted"] = True
        except BaseException as error:
            result["cleanupErrors"].append("logs_" + type(error).__name__)
        try:
            after = host_fingerprint()
            result["hostFilesUnchanged"] = before is not None and after == before
            save("HOST-AFTER.json", after)
            result["sourceUnchanged"] = all(digest(repo / path) == value for path, value in pins.items())
            probe = json.loads((area / "PROBE-RESULT.json").read_text())
            result["probeStatus"] = probe.get("status")
            result["probeCleanupConfirmed"] = probe.get("cleanupErrors") == [] and probe.get("aliveAfterCleanup") == []
        except BaseException as error:
            result["cleanupErrors"].append("readback_" + type(error).__name__)
        if (result["firstError"] is None and not result["cleanupErrors"] and result.get("exitCode") == 0
                and result.get("ownedProcessesGone") and result.get("hostFilesUnchanged") and result.get("sourceUnchanged")
                and result.get("probeCleanupConfirmed") and result.get("probeStatus") == "PASS_SOURCE_WAYLAND_NATIVE_AUDIO_REHOSTING"):
            result["status"] = "PASS_ISOLATED_NATIVE_AUDIO"
        else:
            result["status"] = "FAILED"
        save("RUNNER-RESULT.json", result)
        print(json.dumps(result))
    return 0 if result["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
