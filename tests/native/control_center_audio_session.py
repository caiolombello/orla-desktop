#!/usr/bin/python3
"""KWin's private session child; the outer runner owns all process cleanup."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

area = Path(__file__).resolve().parent
repo = Path(os.environ["ORLA_NATIVE_REPO"])
for key, directory in (("XDG_RUNTIME_DIR", "run"), ("XDG_CONFIG_HOME", "config"),
                       ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
    assert Path(os.environ[key]).resolve() == area / directory, "strict_private_xdg"
assert os.environ["WAYLAND_DISPLAY"] == "orla-model", "private_wayland_required"
assert os.environ["DBUS_SESSION_BUS_ADDRESS"] != os.environ["ORLA_PARENT_BUS"], "private_bus_required"
assert os.environ["PULSE_SERVER"] == "unix:" + str(area / "run/pulse-native"), "private_audio_required"
assert not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_SOCKET"), "no_host_display"
env = dict(os.environ, QT_QPA_PLATFORM="wayland", QT_QUICK_BACKEND="software")
with (area / "AUDIO.stdout").open("x") as stdout, (area / "AUDIO.stderr").open("x") as stderr:
    audio = subprocess.Popen(["pipewire", "-c", str(area / "config/audio-server.conf")],
                             env=env, stdout=stdout, stderr=stderr)
with (area / "AUDIO-PID.json").open("x") as stream:
    json.dump({"pid": audio.pid}, stream)
deadline = time.monotonic() + 5
while not (area / "run/pulse-native").is_socket():
    assert audio.poll() is None and time.monotonic() < deadline, "private_audio_not_ready"
    time.sleep(0.02)
probe = repo / "tests/native/control_center_audio.py"
os.execve(sys.executable, [sys.executable, "-B", str(probe), "--area", str(area)], env)
