"""Native CC integration in an owned Wayland/bus/audio session, never session audio.

Requires a private PipeWire server containing only orla_fixture_a/b. These null
sinks advertise node.virtual=false to exercise PlasmaPA's admitted-sink path;
they are protocol fixtures, not physical hardware. See the validation guide.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import time

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl, qVersion
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QSignalSpy, QTest
from shiboken6 import isValid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", required=True)
    args = parser.parse_args()
    area = Path(args.area)
    repo = Path(__file__).resolve().parents[2]
    result = {"status": "PREPARING", "firstError": None, "cleanupErrors": [],
              "scope": "Source Wayland and real PlasmaPA/private PipeWire; synthetic sinks only"}
    trace, violations, warnings, presentations = [], [], [], []
    alive = set()
    created, destroyed = [], []
    engine = app = popup = dialog = loader = None
    receipts = announcements = None
    phase = None
    deadline = time.monotonic() + 25

    def require(condition, code):
        if not condition:
            raise AssertionError(code)

    def preserve_error(error):
        if result["firstError"] is None:
            result["firstError"] = {"type": type(error).__name__,
                                    "code": str(error) if isinstance(error, AssertionError) else "fixture_exception",
                                    "phase": phase}

    def evaluate(target, code):
        expression = QQmlExpression(QQmlEngine.contextForObject(target), target, code)
        value, _ = expression.evaluate()
        require(not expression.hasError(), "qml_expression_failed")
        return value

    def wait(predicate, code):
        until = min(deadline, time.monotonic() + 4)
        while not predicate():
            require(time.monotonic() < until, code)
            QTest.qWait(5)

    def record(event, token=None):
        require(len(trace) < 256, "trace_bound")
        trace.append({"event": event, "token": token, "alive": sorted(alive),
                      "phase": phase, "popupVisible": bool(popup is not None and isValid(popup)
                                                            and popup.property("visible"))})

    def observe(signal, callback):
        def guarded(*args):
            try:
                callback(*args)
            except BaseException as error:
                preserve_error(error)
                violations.append("observer_" + type(error).__name__)
        signal.connect(guarded)

    def retired(token):
        # QObject.destroyed, not Loader.item=null or Component.onDestruction.
        if token not in alive:
            violations.append("unexpected_backend_destruction")
        alive.discard(token)
        destroyed.append(token)
        record("backend-destroyed", token)

    def backend_changed():
        backend = loader.property("item")
        if backend is None:
            record("loader-item-null")
            return
        if alive:
            violations.append("overlapping_native_backends")
        token = len(created) + 1
        created.append(token)
        alive.add(token)
        observe(backend.destroyed, lambda *_, token=token: retired(token))
        record("backend-published", token)

    def host_changed():
        if alive:
            violations.append("host_changed_before_backend_destroyed")
        if dialog is not None and isValid(dialog) and (dialog.isVisible() or dialog.activeFocusItem() is not None
                                                      or QGuiApplication.focusWindow() == dialog):
            violations.append("host_changed_before_native_keyboard_departure")
        record("host-changed")

    def about_to_hide():
        if audio.property("pendingKind") or audio.property("volumeGestureActive"):
            violations.append("audio_not_cancelled_before_close")
        record("about-to-hide-audio-cleared")

    def event_presented():
        event = json.loads(evaluate(events, "JSON.stringify(current)"))
        if event is not None:
            require(event["kind"] == "audio", "unexpected_event_kind")
            presentations.append({k: event[k] for k in ("action", "targetId", "value")})

    def server_readback():
        command = ["pactl", "--server=" + os.environ["PULSE_SERVER"], "--format=json", "list", "sinks"]
        response = subprocess.run(command, capture_output=True, text=True, timeout=3)
        require(response.returncode == 0, "private_server_readback_failed")
        sinks = json.loads(response.stdout)
        require({s["name"] for s in sinks} == {"orla_fixture_a", "orla_fixture_b"},
                "private_server_has_unexpected_sink")
        return {s["name"]: {"raw": {v["value"] for v in s["volume"].values()}, "muted": s["mute"]}
                for s in sinks}

    try:
        require(area.is_absolute() and area.is_dir() and not area.is_symlink(), "owned_area_required")
        require(area.stat().st_uid == os.getuid() and stat.S_IMODE(area.stat().st_mode) == 0o700,
                "owned_area_mode")
        area = area.resolve()
        for key in ("XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            path = Path(os.environ[key]).resolve()
            require(path != area and path.is_relative_to(area), "private_xdg_required")
        require(os.environ.get("WAYLAND_DISPLAY") == "orla-model", "private_wayland_required")
        require(not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_SOCKET"), "no_host_display")
        require(os.environ.get("DBUS_SESSION_BUS_ADDRESS")
                and os.environ["DBUS_SESSION_BUS_ADDRESS"] != os.environ.get("ORLA_PARENT_BUS"),
                "private_session_bus_required")
        require(os.environ.get("PULSE_SERVER") == "unix:" + str(area / "run/pulse-native"),
                "explicit_private_pulse_server_required")
        require(os.environ.get("PULSE_CLIENTCONFIG") == str(area / "config/pulse-client.conf"),
                "private_pulse_config_required")
        require((area / "config/pulse-client.conf").read_text() ==
                "autospawn = no\ndefault-server = " + os.environ["PULSE_SERVER"] + "\n",
                "pulse_autospawn_must_be_disabled")
        require((area / "run/pulse-native").is_socket(), "private_pulse_socket_required")
        app = QGuiApplication([])
        QGuiApplication.setDesktopFileName("org.orla.ModelProbe")
        require(app.platformName() == "wayland", "actual_wayland_required")
        result["qtVersion"] = qVersion()
        result["platformName"] = app.platformName()
        engine = QQmlApplicationEngine()
        engine.warnings.connect(lambda values: warnings.extend("qml_warning" for _ in values))
        engine.load(QUrl.fromLocalFile(str(repo / "tests/QmlHarness.qml")))
        require(len(engine.rootObjects()) == 1, "dock_fixture_load")
        window = engine.rootObjects()[0]
        window.setWidth(720)
        window.setHeight(560)
        dock = window.findChild(QQuickItem, "dock")
        config = window.findChild(QObject, "configuration")
        popup = window.findChild(QQuickItem, "controlCenterPopup")
        center = window.findChild(QQuickItem, "controlCenterContents")
        audio = window.findChild(QObject, "audioControlState")
        events = window.findChild(QObject, "localEventState")
        loader = window.findChild(QObject, "controlCenterAudioNativeLoader")
        anchor = window.findChild(QQuickItem, "controlCenterButton")
        require(all(item is not None for item in (dock, config, popup, center, audio, events, loader, anchor)),
                "fixture_objects_missing")
        config.setProperty("showControlCenter", True)
        config.setProperty("showAudioHud", True)
        require(dock.setProperty("nativePopups", True), "native_popups_required")
        require(evaluate(dock, "(audioBackendOverride = null) === null"), "real_audio_backend_required")
        require(loader.property("item") is None, "backend_loaded_before_open")
        engine.load(QUrl.fromLocalFile(str(repo / "tests/SharedControlCenterBarHarness.qml")))
        require(len(engine.rootObjects()) == 2, "bar_fixture_load")
        bar_window = engine.rootObjects()[1]
        bar_window.setWidth(720)
        bar_window.setHeight(560)
        bar = bar_window.findChild(QQuickItem, "sharedControlCenterBar")
        host = bar_window.findChild(QQuickItem, "sharedControlCenterHost")
        entry = bar_window.findChild(QObject, "sharedControlCenterEntry")
        require(host.setProperty("nativePopups", True), "bar_native_popups_required")
        wait(lambda: entry.property("available") and popup.property("nativeDialog") is not None,
             "entry_not_ready")
        dialog = popup.property("nativeDialog")
        context = engine.rootContext()
        for name, value in (("ownedAudio", audio), ("ownedEntry", entry), ("ownedBar", bar),
                            ("ownedPopup", popup), ("ownedAnchor", anchor), ("ownedCenter", center)):
            context.setContextProperty(name, value)
        observe(loader.itemChanged, backend_changed)
        observe(loader.activeChanged, lambda: record("loader-active" if loader.property("active") else "loader-inactive"))
        observe(popup.hostChanged, host_changed)
        observe(popup.aboutToHide, about_to_hide)
        observe(popup.closed, lambda: record("popup-closed"))
        observe(events.currentChanged, event_presented)
        signal = audio.metaObject().method(audio.metaObject().indexOfSignal("confirmed(QVariant)"))
        receipts = QSignalSpy(audio, signal)
        require(receipts.isValid(), "confirmation_spy_invalid")
        signal = events.metaObject().method(events.metaObject().indexOfSignal("announcementRequested(QVariant)"))
        announcements = QSignalSpy(events, signal)
        require(announcements.isValid(), "announcement_spy_invalid")

        def ready(target):
            return (popup.property("host") == target and popup.property("visible") and dialog.isVisible()
                    and QGuiApplication.focusWindow() == dialog and dialog.activeFocusItem() is not None
                    and audio.property("status") == "ready" and audio.property("writable"))

        def snapshot():
            return json.loads(evaluate(audio, "JSON.stringify(backend.snapshot)"))

        require(evaluate(popup, "openAt(ownedAnchor)") is True, "initial_open_rejected")
        wait(lambda: ready(dock), "initial_native_ready")
        before = snapshot()
        require({o["id"] for o in before["outputs"]} == {"orla_fixture_a", "orla_fixture_b"},
                "foreign_or_missing_output")
        require(before["defaultOutputId"] == "orla_fixture_a", "initial_default_output")
        require(all(o["volumeRaw"] == 65536 and not o["muted"] for o in before["outputs"]),
                "unexpected_initial_audio_state")
        require(all(s == {"raw": {65536}, "muted": False} for s in server_readback().values()),
                "initial_server_state_changed")
        require(created == [1] and alive == {1}, "initial_backend_count")
        require(receipts.count() == 0 and events.property("count") == 0, "opening_emitted_confirmation")
        record("initial-ready")

        # One JS frame: accepted native write is still pending when rehosting starts.
        phase = "pending-dock-to-bar"
        pending = json.loads(evaluate(popup, """JSON.stringify((function() {
            const began = ownedAudio.beginVolumeGesture();
            const sent = ownedAudio.requestGestureVolume(80);
            const pendingBefore = ownedAudio.pendingKind;
            const gestureBefore = ownedAudio.volumeGestureActive;
            const accepted = ownedBar.toggleControlCenter();
            return {began, sent, pendingBefore, gestureBefore, accepted,
                pendingAfter: ownedAudio.pendingKind, gestureAfter: ownedAudio.volumeGestureActive};
        })())"""))
        require(pending == {"began": True, "sent": True, "pendingBefore": "volume", "gestureBefore": True,
                            "accepted": True, "pendingAfter": "", "gestureAfter": False},
                "pending_transfer_not_established_or_cancelled")
        result["pendingTransfer"] = pending
        wait(lambda: ready(host), "bar_rehost_not_ready")
        wait(lambda: audio.property("confirmedVolume") == 80, "cancelled_write_readback_not_seen")
        require(receipts.count() == 0 and events.property("count") == 0, "cancelled_write_emitted_hud")
        require(not presentations and announcements.count() == 0, "cancelled_write_was_presented")
        require(server_readback()["orla_fixture_a"]["raw"] == {52429}, "cancelled_write_server_readback")
        require(created == [1, 2] and destroyed == [1] and alive == {2}, "bar_backend_lifetime")
        require(evaluate(popup, "contents === ownedCenter") and center.property("audio") == audio,
                "view_or_audio_owner_replaced")
        record("cancelled-write-observed-without-confirmation")

        require(evaluate(audio, "requestVolume(60)") is True, "new_volume_rejected")
        wait(lambda: receipts.count() == 1 and audio.property("confirmedVolume") == 60,
             "new_volume_unconfirmed")
        require(events.property("count") == 1, "new_volume_hud_count")
        require(presentations == [{"action": "volume", "targetId": "orla_fixture_a", "value": 60}],
                "new_volume_not_presented_exactly_once")
        wait(lambda: announcements.count() == 1, "new_volume_accessible_announcement_missing")
        require(server_readback()["orla_fixture_a"]["raw"] == {39322}, "new_volume_server_readback")
        receipt = receipts.at(0)[0]
        if hasattr(receipt, "toVariant"):
            receipt = receipt.toVariant()
        require(receipt["action"] == "volume" and receipt["targetId"] == "orla_fixture_a"
                and receipt["value"] == 60, "new_volume_wrong_receipt")
        result["confirmedReceipt"] = {k: receipt[k] for k in ("action", "targetId", "value")}
        record("new-volume-confirmed-once")

        phase = "bar-to-dock"
        require(evaluate(popup, "openAt(ownedAnchor)") is True, "return_transfer_rejected")
        wait(lambda: ready(dock), "dock_rehost_not_ready")
        require(created == [1, 2, 3] and destroyed == [1, 2] and alive == {3}, "dock_backend_lifetime")
        require(audio.property("confirmedVolume") == 60 and receipts.count() == 1,
                "return_transfer_changed_confirmed_state")
        require(evaluate(popup, "contents === ownedCenter") and center.property("audio") == audio,
                "return_view_or_audio_owner_replaced")
        record("returned-to-dock")

        phase = "final-close"
        evaluate(popup, "closeSession()")
        wait(lambda: not popup.property("visible") and not dialog.isVisible() and not alive,
             "final_backend_not_retired")
        require(created == destroyed == [1, 2, 3], "final_backend_count")
        require(not audio.property("pendingKind") and not audio.property("volumeGestureActive"),
                "final_audio_pending")
        require(receipts.count() == 1 and announcements.count() == 1 and len(presentations) == 1,
                "final_close_duplicated_confirmation_or_presentation")
        require(not violations and not warnings, "observed_warning_or_lifecycle_violation")
        result["createdBackends"] = created
        result["destroyedBackends"] = destroyed
        result["status"] = "PASS_SOURCE_WAYLAND_NATIVE_AUDIO_REHOSTING"
    except BaseException as error:
        result["status"] = "FAILED"
        preserve_error(error)
    finally:
        phase = None
        try:
            if engine is not None:
                for window in reversed(engine.rootObjects()):
                    window.close()
                    window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                engine.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                app.processEvents()
        except BaseException as error:
            result["cleanupErrors"].append("engine_" + type(error).__name__)
        result.update(trace=trace, violations=violations, warningCount=len(warnings),
                      aliveAfterCleanup=sorted(alive),
                      confirmations=receipts.count() if receipts is not None else None,
                      announcements=announcements.count() if announcements is not None else None,
                      presentations=presentations,
                      claimsExcluded=["installed_user_session", "physical_input", "hardware_audio",
                                      "native_setter_counts", "complete_native_matrix"])
        if result["cleanupErrors"] or alive or violations or warnings or result["firstError"] is not None:
            result["status"] = "FAILED"
        if result["status"].startswith("PASS_") and (receipts.count() != 1 or announcements.count() != 1
                                                     or len(presentations) != 1):
            result["status"] = "FAILED"
            result["cleanupErrors"].append("cleanup_duplicated_confirmation_or_presentation")
        with (area / "PROBE-RESULT.json").open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    return 0 if result["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
