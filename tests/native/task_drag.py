"""Real Qt events on the owned fixture; no state finish/cancel helper calls."""
import json
import time
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QSignalSpy, QTest

A="org.orla.ModelA"
B="org.orla.ModelB"
def run_gestures(window,config,dock,evaluate,snapshot,record,result,capture_dir):
    cases=[];result["gestureCases"]=cases;held=False;tool=None;last=QPoint()
    def settle(predicate):
        deadline=time.monotonic()+3
        while not predicate():
            if time.monotonic()>=deadline:raise AssertionError("gesture_condition_deadline")
            QTest.qWait(10)
    def focus_window():
        window.requestActivate();settle(window.isActive)
    def named(name):
        value=evaluate("(function find(item) { if(item.objectName === "+json.dumps(name)+") return item; for(let child of item.children) {let found=find(child);if(found)return found;}return null;})(this)")
        assert value is not None,"gesture_control_missing"
        return value
    def tile(identity):
        rows=[r for r in snapshot()["rows"] if r["id"]==identity]
        assert len(rows)==1,"gesture_identity_ambiguous"
        name="taskTile"+str(rows[0]["row"])
        return named(name)
    def point(item,x=.5):return item.mapToScene(QPointF(item.width()*x,item.height()/2)).toPoint()
    def order():return [r["id"] for r in snapshot()["rows"]]
    def saved():return evaluate("JSON.stringify(Array.from(profiles.effective.launchers))")
    def focus_fact(identity):
        value=window.activeFocusItem();own=tile(identity)
        return {"sourceTileFocused":own.hasActiveFocus(),"hasOwnWindowFocusItem":value is not None,"windowActive":window.isActive()}
    def move(p):
        nonlocal last
        last=p;QTest.mouseMove(window,p,10);QTest.qWait(10)
    def press(identity):
        nonlocal held,last
        focus_window();item=tile(identity);item.forceActiveFocus();QTest.qWait(20)
        before_focus=focus_fact(identity)
        start=point(item);last=start
        QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,start);held=True
        move(QPoint(start.x()+18,start.y()))
        assert evaluate("taskDrag.active"),"gesture_threshold_not_active"
        return item,start,before_focus
    def release(p):
        nonlocal held,last
        last=p;QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,p);held=False;QTest.qWait(50)
    def run(name,source,target,mode="save"):
        before=order();raw=saved();source_item=tile(source);clicked=QSignalSpy(source_item.clicked)
        legacy=evaluate("profiles.activeProfileId")=="legacy"
        signal=config.launchersChanged if legacy else config.profilesJSONChanged
        spy=QSignalSpy(signal)
        newer=None
        if mode=="newer-focus":
            newer=lambda:named("settingsButton").forceActiveFocus()
            signal.connect(newer)
        result["gestureInProgress"]={"case":name,"mode":mode,"beforeOrder":before}
        item,start,pre_focus=press(source)
        try:
            left,right=sorted([tile(A),tile(B)],key=lambda value:point(value).x())
            left_edge=left.mapToScene(QPointF(left.width(),left.height()/2));right_edge=right.mapToScene(QPointF(0,right.height()/2))
            gap=right_edge.x()-left_edge.x();assert abs(gap-5)<=.1,"fixture_gap_not_five_pixels"
            gap_point=QPoint(round((left_edge.x()+right_edge.x())/2),round(left_edge.y()))
            move(gap_point)
            assert evaluate("taskDrag.active") and evaluate("taskDrag.destination")=="","gap_canceled_gesture_or_kept_destination"
            assert spy.count()==0 and clicked.count()==0 and order()==before,"held_gap_mutation_or_activation"
            destination=point(tile(target),.8 if before.index(source)<before.index(target) else .2)
            move(destination)
            assert spy.count()==0 and clicked.count()==0 and order()==before,"held_destination_mutation_or_activation"
            marker=named("taskDropIndicator")
            assert marker.isVisible(),"held_destination_marker_missing"
            if name in ("managed-forward","managed-reverse"):
                image=window.grabWindow();assert not image.isNull(),"held_capture_unavailable"
                origin=dock.mapToScene(QPointF(0,0));ratio=image.devicePixelRatio()
                rect=QRect(round(origin.x()*ratio),round(origin.y()*ratio),round(dock.width()*ratio),round(dock.height()*ratio))
                assert image.copy(rect).save(str(capture_dir/(name+"-held.png"))),"held_capture_failed"
            if mode=="self":
                destination=point(tile(source));move(destination)
            elif mode=="escape":
                # Delivery goes through the fixture and Source Keys handler, not state.cancel().
                QTest.keyClick(window,Qt.Key_Escape);QTest.qWait(10)
                assert not evaluate("taskDrag.pressed"),"delivered_escape_did_not_cancel"
            elif mode=="outside":
                move(QPoint(-5,destination.y()));move(destination)
                assert not evaluate("taskDrag.pressed"),"outside_return_rearmed"
            elif mode=="revision":
                assert evaluate("profiles.commitPresentation({calendarEvents:!profiles.effective.calendarEvents},profiles.activeProfileId,profiles.revision)") is True
                assert not evaluate("taskDrag.pressed"),"revision_did_not_cancel"
            elif mode=="deactivate":
                topology=evaluate("JSON.stringify(taskOrder())")
                tool.requestActivate();settle(lambda:not window.isActive())
                assert evaluate("JSON.stringify(taskOrder())")==topology,"focus_case_changed_task_topology"
                assert not evaluate("taskDrag.pressed"),"window_deactivation_did_not_cancel"
            release(destination)
            expected=list(reversed(before)) if mode in ("save","newer-focus") else before
            settle(lambda:order()==expected)
            result["gestureInProgress"].update(setterSignals=spy.count(),clickedSignals=clicked.count(),afterOrder=order(),focusAfter=focus_fact(source))
            if mode=="save" and pre_focus["sourceTileFocused"]:
                assert focus_fact(source)["sourceTileFocused"],"DROP_LOST_FOCUSED_TILE"
            if mode=="newer-focus":
                assert named("settingsButton").hasActiveFocus(),"drop_stole_newer_control_focus"
            assert not marker.isVisible(),"terminal_marker_leaked"
            expected_writes=1 if mode in ("save","newer-focus","revision") else 0
            assert spy.count()==expected_writes and clicked.count()==0,"release_write_or_activation_count"
            if mode not in ("save","newer-focus"):assert saved()==raw,"canceled_gesture_changed_saved_launchers"
            cases.append({"case":name,"mode":mode,"gapLogicalPx":gap,"gapPoint":[gap_point.x(),gap_point.y()],
                "setterSignals":spy.count(),"clickedSignals":clicked.count(),"beforeOrder":before,"afterOrder":order(),
                "focusBefore":pre_focus,"focusAfter":focus_fact(source)})
            record("gesture-"+name)
        finally:
            if held:release(last)
            if newer is not None:signal.disconnect(newer)
    try:
        # Create/settle the owned Tool before the focus-loss hold, avoiding insertion as the cancel witness.
        tool=QQuickWindow();tool.setFlags(Qt.Tool);tool.setObjectName("ownedGestureFocusTool");tool.resize(120,80);tool.show()
        settle(tool.isExposed);focus_window();QTest.qWait(100)
        assert evaluate("profiles.commitPresentation({appearance:{theme:'midnight'}},profiles.activeProfileId,profiles.revision)")
        QTest.qWait(150)
        run("managed-forward",A,B)
        assert evaluate("profiles.commitPresentation({appearance:{theme:'paper'}},profiles.activeProfileId,profiles.revision)")
        QTest.qWait(150)
        run("managed-reverse",B,A)
        run("newer-control-focus",A,B,"newer-focus")
        run("restore-managed-order",B,A)
        run("self-drop",A,A,"self")
        run("delivered-escape",A,B,"escape")
        run("outside-and-return",A,B,"outside")
        run("held-profile-revision",A,B,"revision")
        run("own-window-deactivation",A,B,"deactivate")
        focus_window();item=tile(A);clicks=QSignalSpy(item.clicked);spy=QSignalSpy(config.profilesJSONChanged)
        QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point(item));QTest.qWait(50)
        assert clicks.count()==1 and spy.count()==0,"short_click_contract"
        mouse_count=clicks.count()
        focus_window();item=tile(A);item.forceActiveFocus();space=QSignalSpy(item.clicked)
        QTest.keyClick(window,Qt.Key_Space);QTest.qWait(50)
        assert space.count()==1 and spy.count()==0,"space_contract"
        cases.append({"case":"short-click-and-space","mouseClickedSignals":mouse_count,"spaceClickedSignals":space.count(),"setterSignals":spy.count()})
        assert evaluate("profiles.select('legacy',profiles.activeProfileId,profiles.revision)")
        QTest.qWait(50)
        run("legacy-forward",A,B)
        run("legacy-reverse",B,A)
        assert not evaluate("taskDrag.pressed"),"gesture_ticket_leaked"
        return cases
    finally:
        if held:release(last)
        if tool is not None:tool.close();tool.deleteLater();QTest.qWait(20)
