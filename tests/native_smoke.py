"""Exercise only an owned test window through Plasma's real Wayland backend."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def main():
    root = Path(__file__).resolve().parents[1]
    evidence = root / ".runtime"
    evidence.mkdir(exist_ok=True)
    screenshot = evidence / "caiodock-native.png"
    with tempfile.TemporaryDirectory(prefix="caiodock-native-") as temporary:
        temp = Path(temporary)
        package = temp / "package"
        probe = temp / "probe.py"
        shutil.copyfile(root / "tests/probe_window.py", probe)
        launcher = temp / "data/applications/caiodock-acceptance.desktop"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("[Desktop Entry]\nType=Application\nName=CaioDock acceptance probe\nIcon=preferences-desktop-launch-feedback\nExec=\"" + sys.executable + "\" \"" + str(probe) + "\"\n")
        shutil.copytree(root / "package", package)
        # Calendar/caches have their own isolated tests. This probe exercises
        # only its owned native window, without activating personal data sources.
        config_file = package / "contents/config/main.xml"
        config = ET.parse(config_file)
        namespace = {"k": "http://www.kde.org/standards/kcfg/1.0"}
        for entry in config.findall(".//k:entry", namespace):
            if entry.get("name") in ("calendarEvents", "showQuota", "showPeripherals", "showRecording"):
                entry.find("k:default", namespace).text = "false"
        config.write(config_file, encoding="utf-8", xml_declaration=True)
        shutil.copyfile(root / "tests/NativeChecks.qml", package / "contents/ui/NativeChecks.qml")
        main_qml = package / "contents/ui/main.qml"
        source = main_qml.read_text()
        source = source.rstrip()[:-1] + "\nNativeChecks { targetDock: dock; screenshotPath: " + json.dumps(str(screenshot)) + "; launcherUrl: " + json.dumps(launcher.as_uri()) + " }\n}\n"
        main_qml.write_text(source)
        env = os.environ.copy()
        env.update(XDG_DATA_HOME=str(temp / "data"), XDG_CONFIG_HOME=str(temp / "config"),
                   XDG_CACHE_HOME=str(temp / "cache"), QT_QPA_PLATFORM="wayland", QT_FORCE_STDERR_LOGGING="1")
        for key in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            Path(env[key]).mkdir(exist_ok=True)
        subprocess.run(["kpackagetool6", "--type", "Plasma/Applet", "--install", str(package)], env=env, check=True, capture_output=True)
        stopped_by_runner = False
        try:
            result = subprocess.run(["plasmawindowed", "org.caiodock.dock"], env=env, text=True, capture_output=True, timeout=23)
            output = result.stdout + result.stderr
            exit_code = result.returncode
        except subprocess.TimeoutExpired as error:
            # Plasma may deliberately ignore an applet's Qt.quit(). Kill only
            # this owned preview process and inspect the completed test receipt.
            output = (error.stdout or b"") + (error.stderr or b"")
            if isinstance(output, bytes):
                output = output.decode(errors="replace")
            exit_code = None
            stopped_by_runner = True
        marker = "CAIODOCK_NATIVE_RESULT "
        matches = [line.split(marker, 1)[1] for line in output.splitlines() if marker in line]
        if not matches:
            raise RuntimeError("Native test did not finish: " + output)
        report = json.loads(matches[-1])
        report["exit_code"] = exit_code
        report["stopped_by_runner"] = stopped_by_runner
        errors = [line for line in output.splitlines() if "TypeError" in line or "ReferenceError" in line or "Cannot assign" in line]
        report["qml_errors"] = errors
        (evidence / "native-smoke.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False))
        if not report["success"] or exit_code not in (None, 0) or errors:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
