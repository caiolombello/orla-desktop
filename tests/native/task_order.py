"""Native regression for an isolated KWin/DBus/XDG session; no task activation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from PySide6.QtCore import QObject, QUrl, QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QSignalSpy, QTest

PRIVATE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument("--area",required=True)
cases=parser.add_mutually_exclusive_group()
cases.add_argument("--gesture",action="store_true",help="exercise pointer/keyboard cancellation on the owned fixture")
cases.add_argument("--viewport",action="store_true",help="exercise scrolled/clipped/event-covered drags on three owned apps")
cases.add_argument("--competing-move",action="store_true",help="refuse a synchronous second native move")
args=parser.parse_args();AREA=Path(args.area)
IDS=("org.orla.ModelA","org.orla.ModelB") + (("org.orla.ModelC",) if args.competing_move or args.viewport else ())
ORIGINAL=["applications:"+id+".desktop" for id in IDS]
workers=[];warnings=[];facts=[];errors=[];app=None;engine=None;root=None;dock=None
result={"status":"PREPARING","scope":"Actual Source moveTask refusal, synthetic isolated-session windows only"}
def warning(values):
    for value in values:
        if len(warnings)<16:warnings.append(value.toString()[:512])
def evaluate(expression):
    value=QQmlExpression(engine.rootContext(),root,expression)
    answer,_=value.evaluate()
    if value.hasError():raise RuntimeError(value.error().toString()[:512])
    return answer
def snapshot():return json.loads(evaluate("snapshot()"))
def wait(predicate):
    deadline=time.monotonic()+3
    while True:
        value=snapshot()
        if time.monotonic()>=deadline:
            result["deadlineSnapshot"]=value
            raise RuntimeError("model_condition_deadline")
        if predicate(value):return value
        QTest.qWait(20)
def record(stage):
    QTest.qWait(200)
    value=snapshot();facts.append({"stage":stage,**value});return value
def own_rows(value):
    rows=value["rows"]
    assert len(rows)==len(IDS) and {r["id"] for r in rows}==set(IDS),"own_rows_not_unique"
    return {r["id"]:r["row"] for r in rows}
try:
    assert AREA.is_absolute() and not AREA.is_symlink() and AREA.is_dir(),"explicit_private_area_required"
    sandbox=AREA.resolve()
    assert sandbox.stat().st_uid==os.getuid() and sandbox.stat().st_mode & 0o777==0o700,"owned_private_area_required"
    for key in ("XDG_RUNTIME_DIR","XDG_CONFIG_HOME","XDG_DATA_HOME","XDG_CACHE_HOME"):
        directory=Path(os.environ[key]).resolve()
        assert directory!=sandbox and directory.is_relative_to(sandbox),"private_xdg_required"
    assert os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DBUS_SESSION_BUS_ADDRESS"),"isolated_session_required"
    for id in IDS:assert (Path(os.environ["XDG_DATA_HOME"])/"applications"/(id+".desktop")).is_file()
    app=QGuiApplication([])
    if args.viewport: QGuiApplication.setDesktopFileName("org.orla.ModelProbe")
    result["platformName"]=app.platformName();engine=QQmlApplicationEngine();engine.warnings.connect(warning)
    engine.load(QUrl.fromLocalFile(str(PRIVATE/"TaskOrderHarness.qml")))
    assert len(engine.rootObjects())==1,"model_component_unavailable"
    root=engine.rootObjects()[0]
    dock=root.findChild(QObject,"dock");config=root.findChild(QObject,"configuration")
    assert dock is not None and config is not None,"source_fixture_missing"
    root.setProperty("sourceDock",dock)
    config.setProperty("launchers",ORIGINAL)
    def dock_eval(expression):
        value=QQmlExpression(engine.rootContext(),dock,expression);answer,_=value.evaluate()
        if value.hasError():raise RuntimeError(value.error().toString()[:512])
        return answer
    if args.viewport:
        for flag in ("showClock", "showMusic", "showSystemBattery", "showPomodoro", "showQuota",
                     "showPeripherals", "showRecording", "showControlCenter", "showLocalToasts", "showAudioHud"):
            config.setProperty(flag, False)
    assert dock_eval("profiles.initializeDefaults(profiles.activeProfileId,profiles.revision)") is True
    assert dock_eval("profiles.select('work',profiles.activeProfileId,profiles.revision)") is True
    wait(lambda s:len(s["rows"])==len(IDS) and all(r["IsLauncher"] and not r["IsWindow"] for r in s["rows"]))
    record("dormant-source-baseline")
    for label in (id[-1] for id in IDS):
        with (AREA/("Model"+label+".stderr")).open("xb") as stderr:
            workers.append(subprocess.Popen([sys.executable,"-I","-B",str(PRIVATE/"task_order_window.py"),label],env=dict(os.environ),stdout=subprocess.DEVNULL,stderr=stderr))
    wait(lambda s:len(s["rows"])==len(IDS) and {r["id"] for r in s["rows"]}==set(IDS) and all(r["IsWindow"] and r["HasLauncher"] for r in s["rows"]))
    if args.competing_move: dock_eval("reloadLaunchers()")
    current=record("running-source-baseline");indices=own_rows(current)
    if args.viewport:
        for position, identity in enumerate(IDS):
            current = snapshot(); current_indices = own_rows(current)
            if current_indices[identity] != position:
                assert evaluate("normalize(%d,%d)" % (current_indices[identity], position)) is True
        current = snapshot(); indices = own_rows(current)
    if indices[IDS[0]]>indices[IDS[1]]:
        assert evaluate("normalize(%d,%d)"%(indices[IDS[0]],indices[IDS[1]])) is True
    current=record("running-normalized-source-baseline");indices=own_rows(current)
    assert [r["id"] for r in current["rows"]]==list(IDS),"setup_order_not_normalized"
    expected=json.dumps(ORIGINAL,separators=(",",":"))
    result["savedLaunchersBefore"]=evaluate("savedLaunchers()")
    assert result["savedLaunchersBefore"]==expected,"setup_saved_order_not_AB"
    if args.viewport:
        from task_viewport import run_viewport
        result["scope"]="Source viewport Qt pointer gesture matrix; three owned synthetic apps in isolated KWin only"
        result["failureStage"]="VIEWPORT_GESTURE_MATRIX"
        run_viewport(root,config,dock,dock_eval,snapshot,record,result)
        assert not warnings,"qml_warnings"
        result["status"]="PASS_SOURCE_TASK_VIEWPORT_GESTURES"
    elif args.competing_move:
        evaluate("armCompeting()")
        writes=QSignalSpy(config.profilesJSONChanged)
        result["failureStage"]="ASSERT_COMPETING_MOVE_REFUSAL"
        assert dock_eval("taskDrag.begin(taskOrder()[%d].identity)" % indices[IDS[0]])
        assert dock_eval("taskDrag.activate()")
        assert dock_eval("taskDrag.update(taskOrder()[%d].identity,true)" % indices[IDS[1]])
        result["finishReturn"]=dock_eval("taskDrag.finish()")
        current=record("after-competing-move")
        result["competingMoved"]=root.property("competingMoved")
        result["setterSignals"]=writes.count()
        result["savedAfter"]=evaluate("savedLaunchers()")
        result["orderAfter"]=[row["id"] for row in current["rows"]]
        assert result["competingMoved"] is True,"nested_move_not_observed"
        assert result["finishReturn"] is False and writes.count()==0,"COMPETING_MOVE_WAS_PUBLISHED"
        assert result["savedAfter"]==expected and result["orderAfter"]==list(IDS),"refusal_not_reconciled"
        assert not warnings,"qml_warnings"
        result["status"]="PASS_SOURCE_COMPETING_MOVE_REFUSED"
    elif args.gesture:
        from task_drag import run_gestures
        result["scope"]="Source Qt event gestures; owned synthetic windows in isolated KWin only"
        result["failureStage"]="GESTURE_MATRIX"
        result["gestureCases"]=run_gestures(root,config,dock,dock_eval,snapshot,record,result,AREA)
        assert not warnings,"qml_warnings"
        result["status"]="PASS_SOURCE_TASK_DRAG_GESTURES"
    else:
        before_revision=dock_eval("profiles.revision")
        write_spy=QSignalSpy(config.profilesJSONChanged)
        evaluate("armRefusal()")
        result["failureStage"]="ASSERT_SOURCE_REFUSAL_ROLLBACK"
        result["moveTaskReturn"]=dock_eval("moveTask(%d,%d)"%(indices[IDS[0]],indices[IDS[1]]))
        evaluate("disarm()")
        current=record("after-actual-source-refusal")
        result["observerCalls"]=root.property("observerCalls")
        result["observerAccepted"]=root.property("observerAccepted")
        result["configurationSetterSignals"]=write_spy.count()
        result["revisionAdvanced"]=dock_eval("profiles.revision")>before_revision
        result["savedLaunchersAfter"]=evaluate("savedLaunchers()")
        result["visibleOwnOrderAfterRefusal"]=[r["id"] for r in current["rows"]]
        assert result["moveTaskReturn"] is False,"source_did_not_refuse"
        assert result["observerCalls"]==1 and result["observerAccepted"] is True,"observer_did_not_commit_once"
        assert result["configurationSetterSignals"]==1 and result["revisionAdvanced"],"unrelated_commit_not_single_write"
        assert result["savedLaunchersAfter"]==result["savedLaunchersBefore"]==expected,"saved_launcher_bytes_changed"
        own_rows(current)
        assert result["visibleOwnOrderAfterRefusal"]==list(IDS),"SOURCE_REFUSAL_LEFT_RUNNING_ORDER_CHANGED"
        assert not warnings,"qml_warnings"
        result["status"]="PASS_SOURCE_REFUSAL_RESTORES_RUNNING_ORDER"
except BaseException as error:
    result["status"]="FAILED_SOURCE_ASSERTION" if result.get("failureStage") else "FAILED_SETUP";result["firstError"]={"type":type(error).__name__,"message":str(error)[:512]}
finally:
    if root is not None:
        try:evaluate("disarm()")
        except BaseException as error:errors.append("observer:"+type(error).__name__)
    if dock is not None:
        try:result["finalSnapshot"]=snapshot()
        except BaseException as error:result["finalSnapshotError"]=type(error).__name__
    for worker in workers:
        if worker.poll() is None:
            try:worker.terminate()
            except BaseException as error:errors.append(type(error).__name__)
    for worker in workers:
        try:worker.wait(timeout=3)
        except BaseException:
            try:worker.kill();worker.wait(timeout=2)
            except BaseException as error:errors.append(type(error).__name__)
    result["ownedWorkersGone"]=all(worker.poll() is not None for worker in workers)
    result["cleanupErrors"]=errors
    if errors or not result["ownedWorkersGone"]:result["status"]="FAILED_CLEANUP"
    result["facts"]=facts;result["qmlWarnings"]=warnings
    if root is not None:
        root.close();root.deleteLater();QCoreApplication.sendPostedEvents(root,QEvent.DeferredDelete)
        QTest.qWait(10)
    if engine is not None:
        engine.deleteLater();QCoreApplication.sendPostedEvents(engine,QEvent.DeferredDelete)
    if app is not None:app.processEvents()
    with (AREA/"PROBE-RESULT.json").open("x") as stream:json.dump(result,stream,indent=2);stream.write("\n")
sys.exit(0 if result["status"] in ("PASS_SOURCE_REFUSAL_RESTORES_RUNNING_ORDER", "PASS_SOURCE_TASK_DRAG_GESTURES", "PASS_SOURCE_COMPETING_MOVE_REFUSED", "PASS_SOURCE_TASK_VIEWPORT_GESTURES") else 1)
