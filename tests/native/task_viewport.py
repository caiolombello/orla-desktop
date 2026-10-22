"""Viewport drag matrix through owned Qt pointer events in isolated KWin."""
import json
import time
from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QSignalSpy, QTest


def run_viewport(window, config, dock, evaluate, snapshot, record, result):
    held = False
    last = QPoint()
    def settle(predicate):
        deadline = time.monotonic() + 3
        while not predicate():
            if time.monotonic() >= deadline:
                raise AssertionError("viewport_condition_deadline")
            QTest.qWait(10)
    def named(name):
        value = evaluate("(function find(item) { if(item.objectName === " + json.dumps(name)
            + ") return item; for(let child of item.children) {let found=find(child);"
            + "if(found)return found;}return null;})(this)")
        assert value is not None, "viewport_control_missing"
        return value
    viewport = named("appsViewport")
    def tiles():
        return [(row, named("taskTile" + str(row["row"]))) for row in snapshot()["rows"]]
    def rect(item):
        p = item.mapToItem(viewport, QPointF(0, 0))
        return [p.x(), p.y(), item.width(), item.height()]
    def geometry():
        return [viewport.width(), viewport.height(), viewport.property("contentWidth"),
                viewport.property("contentX"), [[row["id"], rect(item)] for row, item in tiles()]]
    def inside(bounds):
        x, y, width, height = bounds
        return width > 0 and height > 0 and x >= 0 and y >= 0 and x + width <= viewport.width() and y + height <= viewport.height()
    def saved():
        return config.property("profilesJSON")
    model = evaluate("tasksModel")
    def model_spies():
        # Keep observing throughout each hold, including mutations rolled back before sampling.
        return {name: QSignalSpy(getattr(model, name)) for name in (
            "rowsAboutToBeMoved", "rowsMoved", "rowsAboutToBeInserted", "rowsInserted",
            "rowsAboutToBeRemoved", "rowsRemoved", "modelAboutToBeReset", "modelReset",
            "layoutAboutToBeChanged", "layoutChanged")}
    def assert_no_model_mutation(spies):
        assert all(spy.isValid() and spy.count() == 0 for spy in spies.values()), "viewport_held_model_structure_changed"
    def move(point):
        nonlocal last
        last = point
        QTest.mouseMove(window, point, 10)
        QTest.qWait(20)
    try:
        assert not evaluate("localEventsActive"), "viewport_first_case_has_event_lane"
        initial = tiles()
        initial_snapshot = snapshot()
        assert len(initial) == 3 and len({row["id"] for row, _ in initial}) == 3, "viewport_requires_unique_ABC"
        assert initial_snapshot["foreignLauncherCount"] == 0, "viewport_foreign_launchers"
        foreign_count = initial_snapshot["foreignRowCount"]
        assert isinstance(foreign_count, int) and foreign_count >= 0, "viewport_invalid_foreign_count"
        gap = rect(initial[1][1])[0] - rect(initial[0][1])[0] - initial[0][1].width()
        assert gap >= 0, "viewport_invalid_gap"
        # Fit a bounded app viewport; scroll settings out of the lane.
        width = initial[0][1].width() + initial[1][1].width() + gap + 8
        dock.setWidth(width + 2 * evaluate("outerMargin"))
        window.setWidth(round(dock.width() + 64))
        QTest.qWait(100)
        maximum = viewport.property("contentWidth") - viewport.width()
        first_x = rect(tiles()[0][1])[0] + viewport.property("contentX")
        assert maximum > 0 and first_x > 0, "viewport_overflow_setup_failed"
        viewport.setProperty("contentX", min(maximum, first_x))
        QTest.qWait(100)
        assert not viewport.property("moving"), "viewport_still_moving"
        assert viewport.property("contentWidth") > viewport.width() and viewport.property("contentX") > 0, "viewport_not_prescrolled"
        visible = [(row, item) for row, item in tiles() if inside(rect(item))]
        pair = next(((left, right) for left, right in zip(visible, visible[1:])
                     if right[0]["row"] == left[0]["row"] + 1), None)
        assert pair is not None, "viewport_no_two_complete_adjacent_apps"
        (source, source_item), (target, target_item) = pair
        window.requestActivate()
        settle(window.isActive)
        before_focus_geometry = geometry()
        source_item.forceActiveFocus()
        QTest.qWait(30)
        assert geometry() == before_focus_geometry, "visible_source_focus_scrolled_fixture"
        before = snapshot()
        before_ids = [row["id"] for row in before["rows"]]
        full_raw = evaluate("JSON.stringify(taskOrder())")
        full_before = json.loads(full_raw)
        assert isinstance(full_before, list) and len(full_before) == 3 + foreign_count, "viewport_full_order_count"
        full_ids = [row["identity"] for row in full_before]
        assert len(set(full_ids)) == len(full_ids), "viewport_full_order_not_unique"
        assert before["foreignRowCount"] == foreign_count, "viewport_setup_foreign_count_changed"
        raw = saved()
        before_geometry = geometry()
        structural = model_spies()
        writes = QSignalSpy(config.profilesJSONChanged)
        legacy_writes = QSignalSpy(config.launchersChanged)
        clicks = [QSignalSpy(item.clicked) for _, item in tiles()]
        start = source_item.mapToScene(QPointF(source_item.width() * .5, source_item.height() / 2)).toPoint()
        destination = target_item.mapToScene(QPointF(target_item.width() * .8, target_item.height() / 2)).toPoint()
        last = start
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        held = True
        move(QPoint(start.x() + 18, start.y()))
        assert evaluate("taskDrag.active"), "viewport_drag_threshold_not_active"
        move(destination)
        QTest.qWait(50)
        marker = named("taskDropIndicator")
        assert marker.isVisible() and inside(rect(marker)), "viewport_marker_not_inside"
        assert snapshot() == before and saved() == raw, "viewport_hold_changed_order_or_saved"
        assert evaluate("JSON.stringify(taskOrder())") == full_raw, "viewport_hold_changed_full_order"
        assert geometry() == before_geometry, "viewport_hold_scrolled"
        assert writes.count() == legacy_writes.count() == 0 and all(spy.count() == 0 for spy in clicks), "viewport_hold_write_or_click"
        expected_ids = list(before_ids)
        moved = expected_ids.pop(before_ids.index(source["id"]))
        expected_ids.insert(expected_ids.index(target["id"]) + 1, moved)
        expected_full_ids = list(full_ids)
        moved_identity = expected_full_ids.pop(source["row"])
        target_identity = full_ids[target["row"]]
        expected_full_ids.insert(expected_full_ids.index(target_identity) + 1, moved_identity)
        expected_document = json.loads(raw)
        active = [profile for profile in expected_document["profiles"]
                  if profile["id"] == expected_document["activeProfileId"]]
        assert len(active) == 1, "viewport_active_saved_profile_missing"
        expected_saved = active[0]["launchers"]
        source_url = "applications:" + source["id"] + ".desktop"
        target_url = "applications:" + target["id"] + ".desktop"
        expected_saved.remove(source_url)
        expected_saved.insert(expected_saved.index(target_url) + 1, source_url)
        assert_no_model_mutation(structural)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, destination)
        held = False
        settle(lambda: [row["id"] for row in snapshot()["rows"]] == expected_ids)
        QTest.qWait(100)
        after = snapshot()
        assert after["foreignRowCount"] == foreign_count and after["foreignLauncherCount"] == 0, "viewport_foreign_count_after_release"
        after_full = json.loads(evaluate("JSON.stringify(taskOrder())"))
        assert [row["identity"] for row in after_full] == expected_full_ids, "viewport_full_identity_splice_wrong"
        assert {row["id"]: row["WinIdList"] for row in after["rows"]} == {row["id"]: row["WinIdList"] for row in before["rows"]}, "viewport_window_identity_changed"
        assert after["launcherList"] == expected_saved and json.loads(saved()) == expected_document, "viewport_saved_splice_wrong"
        assert writes.count() == 1 and legacy_writes.count() == 0 and all(spy.count() == 0 for spy in clicks), "viewport_release_write_or_click"
        assert not evaluate("taskDrag.pressed") and not marker.isVisible(), "viewport_terminal_ticket_or_marker"
        result["viewportCase"] = {"case": "stable-overflow-valid-release", "beforeOrder": before_ids,
            "afterOrder": expected_ids, "source": source["id"], "target": target["id"],
            "foreignRowCount": foreign_count, "fullBeforeOrder": full_ids, "fullAfterOrder": expected_full_ids,
            "geometryBefore": before_geometry, "profilesSetterSignals": writes.count(), "clickedSignals": 0}
        record("viewport-stable-overflow-release")
        result["viewportCases"] = [result["viewportCase"]]

        # Start from the accepted order; never focus the clipped destination.
        window.requestActivate()
        settle(window.isActive)
        first_x = rect(tiles()[0][1])[0] + viewport.property("contentX")
        maximum = viewport.property("contentWidth") - viewport.width()
        assert maximum > 0 and first_x > 0, "partial_destination_no_overflow"
        viewport.setProperty("contentX", min(maximum, first_x))
        QTest.qWait(100)
        current_tiles = tiles()
        complete = [(row, item) for row, item in current_tiles if inside(rect(item))]
        partial = [(row, item) for row, item in current_tiles
                   if 0 <= rect(item)[0] < viewport.width() < rect(item)[0] + item.width()]
        assert complete and len(partial) == 1, "partial_destination_geometry_missing"
        source, source_item = complete[0]
        target, target_item = partial[0]
        assert source["row"] < target["row"], "partial_destination_not_after_source"
        focus_geometry = geometry()
        source_item.forceActiveFocus()
        QTest.qWait(30)
        assert geometry() == focus_geometry and not viewport.property("moving"), "partial_destination_focus_scrolled"
        before = snapshot()
        full_raw = evaluate("JSON.stringify(taskOrder())")
        raw = saved()
        before_geometry = geometry()
        structural = model_spies()
        writes = QSignalSpy(config.profilesJSONChanged)
        legacy_writes = QSignalSpy(config.launchersChanged)
        clicks = [QSignalSpy(item.clicked) for _, item in tiles()]
        bounds = rect(target_item)
        clipped_left = max(0, bounds[0])
        clipped_right = min(viewport.width(), bounds[0] + bounds[2])
        assert 0 < clipped_right - clipped_left < bounds[2], "partial_destination_not_clipped"
        destination = viewport.mapToScene(QPointF((clipped_left + clipped_right) / 2,
                                                  bounds[1] + bounds[3] / 2)).toPoint()
        actual = viewport.mapFromItem(window.contentItem(), QPointF(destination))
        assert clipped_left <= actual.x() < clipped_right and bounds[1] <= actual.y() < bounds[1] + bounds[3], "partial_destination_rounded_point_outside"
        assert 0 <= actual.x() < viewport.width() and 0 <= actual.y() < viewport.height(), "partial_destination_pointer_outside_viewport"
        result["viewportInProgress"] = {"case": "partial-destination-rejected", "source": source["id"],
            "target": target["id"], "targetBounds": bounds, "visibleWidth": clipped_right - clipped_left,
            "pointerInViewport": [actual.x(), actual.y()], "geometryBefore": before_geometry}
        start = source_item.mapToScene(QPointF(source_item.width() / 2, source_item.height() / 2)).toPoint()
        last = start
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        held = True
        move(QPoint(start.x() + 18, start.y()))
        assert evaluate("taskDrag.active"), "partial_destination_threshold_not_active"
        move(destination)
        QTest.qWait(50)
        marker = named("taskDropIndicator")
        assert evaluate("taskDrag.active") and evaluate("taskDrag.destination") == "", "partial_destination_accepted_or_canceled"
        assert not marker.isVisible(), "partial_destination_marker_visible"
        assert snapshot() == before and saved() == raw and evaluate("JSON.stringify(taskOrder())") == full_raw, "partial_destination_hold_mutation"
        assert geometry() == before_geometry, "partial_destination_hold_scrolled"
        assert writes.count() == legacy_writes.count() == 0 and all(spy.count() == 0 for spy in clicks), "partial_destination_hold_write_or_click"
        assert_no_model_mutation(structural)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, destination)
        held = False
        QTest.qWait(100)
        assert snapshot() == before and saved() == raw and evaluate("JSON.stringify(taskOrder())") == full_raw, "partial_destination_release_mutation"
        assert writes.count() == legacy_writes.count() == 0 and all(spy.count() == 0 for spy in clicks), "partial_destination_release_write_or_click"
        assert_no_model_mutation(structural)
        assert not evaluate("taskDrag.pressed") and not marker.isVisible(), "partial_destination_terminal_ticket_or_marker"
        result["viewportCases"].append({**result["viewportInProgress"], "profilesSetterSignals": writes.count(),
                                        "clickedSignals": 0, "fullOrderUnchanged": True, "savedUnchanged": True})
        result.pop("viewportInProgress")
        record("viewport-partial-destination-rejected")

        # The app is wholly inside the viewport; only the event lane excludes it.
        current_tiles = tiles()
        gap = rect(current_tiles[1][1])[0] - rect(current_tiles[0][1])[0] - current_tiles[0][1].width()
        dock.setWidth(sum(item.width() for _, item in current_tiles) + 2 * gap
                      + current_tiles[0][1].width() + 2 * evaluate("outerMargin"))
        window.setWidth(round(dock.width() + 64))
        config.setProperty("showLocalToasts", True)
        QTest.qWait(100)
        assert evaluate("localEventsActive"), "event_destination_lane_not_enabled"
        event_state = dock.findChild(QObject, "localEventState")
        assert event_state is not None, "event_destination_state_missing"
        def event_eval(expression):
            value = QQmlExpression(QQmlEngine.contextForObject(event_state), event_state, expression)
            answer, _ = value.evaluate()
            assert not value.hasError(), value.error().toString()
            return answer
        event_eval("nowProvider = function() { return 1000; }")
        assert event_eval("submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
                          "title:'Foco concluído',detail:'Pausa sintética'},1000)") is True, "event_destination_submit_refused"
        QTest.qWait(100)
        surface = named("localEventSurface")
        close = named("localEventClose")
        assert surface.isVisible() and close.isVisible(), "event_destination_surface_missing"
        window.requestActivate()
        settle(window.isActive)
        first_x = rect(tiles()[0][1])[0] + viewport.property("contentX")
        maximum = viewport.property("contentWidth") - viewport.width()
        assert maximum > 0, "event_destination_no_overflow"
        viewport.setProperty("contentX", min(maximum, first_x))
        QTest.qWait(100)
        overlay = rect(surface)
        close_bounds = rect(close)
        body_right = min(overlay[0] + overlay[2], close_bounds[0])
        candidates = []
        for row, item in tiles():
            bounds = rect(item)
            left = max(0, bounds[0], overlay[0])
            right = min(viewport.width(), bounds[0] + bounds[2], body_right)
            top = max(0, bounds[1], overlay[1])
            bottom = min(viewport.height(), bounds[1] + bounds[3], overlay[1] + overlay[3])
            if inside(bounds) and left < right and top < bottom:
                candidates.append((row, item, [left, top, right, bottom]))
        sources = [(row, item) for row, item in tiles()
                   if inside(rect(item)) and rect(item)[0] + item.width() <= overlay[0]]
        assert sources and len(candidates) == 1, "event_destination_overlap_setup_failed"
        source, source_item = sources[0]
        target, target_item, intersection = candidates[0]
        focus_geometry = geometry()
        source_item.forceActiveFocus()
        QTest.qWait(30)
        assert geometry() == focus_geometry and not viewport.property("moving"), "event_destination_focus_scrolled"
        left, top, right, bottom = intersection
        destination = viewport.mapToScene(QPointF((left + right) / 2, (top + bottom) / 2)).toPoint()
        actual = viewport.mapFromItem(window.contentItem(), QPointF(destination))
        assert left <= actual.x() < right and top <= actual.y() < bottom, "event_destination_rounded_point_outside_body"
        assert inside(rect(target_item)), "event_destination_target_not_whole"
        before = snapshot()
        full_raw = evaluate("JSON.stringify(taskOrder())")
        raw = saved()
        event_raw = event_eval("JSON.stringify({current:current,pending:pending,sequence:sequence})")
        assert event_eval("current !== null && current.kind === 'completion'"), "event_destination_no_current_completion"
        before_geometry = geometry()
        structural = model_spies()
        writes = QSignalSpy(config.profilesJSONChanged)
        legacy_writes = QSignalSpy(config.launchersChanged)
        clicks = [QSignalSpy(item.clicked) for _, item in tiles()]
        result["viewportInProgress"] = {"case": "active-event-destination-rejected", "source": source["id"],
            "target": target["id"], "targetBounds": rect(target_item), "eventBounds": overlay,
            "bodyIntersection": intersection, "pointerInViewport": [actual.x(), actual.y()]}
        start = source_item.mapToScene(QPointF(source_item.width() / 2, source_item.height() / 2)).toPoint()
        last = start
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        held = True
        move(QPoint(start.x() + 18, start.y()))
        assert evaluate("taskDrag.active"), "event_destination_threshold_not_active"
        move(destination)
        QTest.qWait(50)
        marker = named("taskDropIndicator")
        assert not evaluate("taskDrag.pressed") and not marker.isVisible(), "event_destination_did_not_cancel"
        assert snapshot() == before and saved() == raw and evaluate("JSON.stringify(taskOrder())") == full_raw, "event_destination_hold_mutation"
        assert event_eval("JSON.stringify({current:current,pending:pending,sequence:sequence})") == event_raw, "event_destination_hold_changed_event"
        assert geometry() == before_geometry, "event_destination_hold_geometry_changed"
        assert writes.count() == legacy_writes.count() == 0 and all(spy.count() == 0 for spy in clicks), "event_destination_hold_write_or_click"
        assert_no_model_mutation(structural)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, destination)
        held = False
        QTest.qWait(100)
        assert snapshot() == before and saved() == raw and evaluate("JSON.stringify(taskOrder())") == full_raw, "event_destination_release_mutation"
        assert event_eval("JSON.stringify({current:current,pending:pending,sequence:sequence})") == event_raw, "event_destination_release_changed_event"
        assert writes.count() == legacy_writes.count() == 0 and all(spy.count() == 0 for spy in clicks), "event_destination_release_write_or_click"
        assert_no_model_mutation(structural)
        assert not evaluate("taskDrag.pressed") and not marker.isVisible(), "event_destination_terminal_ticket_or_marker"
        result["viewportCases"].append({**result["viewportInProgress"], "profilesSetterSignals": writes.count(),
                                        "clickedSignals": 0, "fullOrderUnchanged": True, "savedUnchanged": True,
                                        "eventIdentitySequencePreserved": True})
        result.pop("viewportInProgress")
        record("viewport-active-event-destination-rejected")

        # Event arrival must cancel immediately, before any further mouse motion.
        event_eval("clear()")
        settle(lambda: not surface.isVisible())
        window.requestActivate()
        settle(window.isActive)
        first_x = rect(tiles()[0][1])[0] + viewport.property("contentX")
        maximum = viewport.property("contentWidth") - viewport.width()
        assert maximum > 0, "event_arrival_no_overflow"
        viewport.setProperty("contentX", min(maximum, first_x))
        QTest.qWait(100)
        future_cover_left = rect(surface)[0]
        candidates = [(row, item) for row, item in tiles()
                      if inside(rect(item)) and rect(item)[0] + item.width() <= future_cover_left]
        assert len(candidates) >= 2, "event_arrival_no_two_uncovered_apps"
        source, source_item = candidates[0]
        target, target_item = candidates[1]
        focus_geometry = geometry()
        source_item.forceActiveFocus()
        QTest.qWait(30)
        assert geometry() == focus_geometry and not viewport.property("moving"), "event_arrival_focus_scrolled"
        before = snapshot()
        full_raw = evaluate("JSON.stringify(taskOrder())")
        raw = saved()
        sequence_before = event_eval("sequence")
        structural = model_spies()
        writes = QSignalSpy(config.profilesJSONChanged)
        legacy_writes = QSignalSpy(config.launchersChanged)
        clicks = [QSignalSpy(item.clicked) for _, item in tiles()]
        start = source_item.mapToScene(QPointF(source_item.width() / 2, source_item.height() / 2)).toPoint()
        destination = target_item.mapToScene(QPointF(target_item.width() * .8, target_item.height() / 2)).toPoint()
        result["viewportInProgress"] = {"case": "event-arrival-cancels-without-rearm", "source": source["id"],
            "target": target["id"], "futureCoverLeft": future_cover_left, "geometryBefore": geometry()}
        last = start
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        held = True
        move(QPoint(start.x() + 18, start.y()))
        assert evaluate("taskDrag.active"), "event_arrival_threshold_not_active"
        move(destination)
        marker = named("taskDropIndicator")
        assert evaluate("taskDrag.active") and evaluate("taskDrag.destination") != "" and marker.isVisible(), "event_arrival_not_valid_before_submit"
        assert snapshot() == before and saved() == raw and evaluate("JSON.stringify(taskOrder())") == full_raw, "event_arrival_presubmit_mutation"
        assert writes.count() == legacy_writes.count() == 0 and all(spy.count() == 0 for spy in clicks), "event_arrival_presubmit_write_or_click"
        assert event_eval("submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
                          "title:'Foco concluído',detail:'Chegada durante arraste'},1000)") is True, "event_arrival_submit_refused"
        settle(surface.isVisible)
        QTest.qWait(50)
        # No move/release has been sent since submit: this observes the visibility signal.
        assert not evaluate("taskDrag.pressed") and not marker.isVisible(), "event_arrival_did_not_cancel_before_motion"
        assert snapshot() == before and saved() == raw and evaluate("JSON.stringify(taskOrder())") == full_raw, "event_arrival_submit_mutation"
        assert writes.count() == legacy_writes.count() == 0 and all(spy.count() == 0 for spy in clicks), "event_arrival_submit_write_or_click"
        event_fact = json.loads(event_eval("JSON.stringify({identity:current.identity,currentSequence:current.sequence,sequence:sequence})"))
        assert event_fact["sequence"] == sequence_before + 1 and event_fact["currentSequence"] == event_fact["sequence"], "event_arrival_sequence_wrong"
        event_eval("clear()")
        settle(lambda: not surface.isVisible())
        assert event_eval("current === null && pending.length === 0 && sequence === " + str(event_fact["sequence"])), "event_arrival_clear_state_wrong"
        reentry = target_item.mapToScene(QPointF(target_item.width() * .35, target_item.height() / 2)).toPoint()
        reentry_local = viewport.mapFromItem(window.contentItem(), QPointF(reentry))
        target_bounds = rect(target_item)
        assert reentry != destination, "event_arrival_reentry_point_not_distinct"
        assert (target_bounds[0] <= reentry_local.x() < target_bounds[0] + target_bounds[2]
                and target_bounds[1] <= reentry_local.y() < target_bounds[1] + target_bounds[3]
                and 0 <= reentry_local.x() < future_cover_left), "event_arrival_reentry_outside_valid_target"
        # Pointer handlers are non-visual delegate resources; use their QML id context.
        centroid_expression = QQmlExpression(QQmlEngine.contextForObject(source_item), source_item,
            "JSON.stringify([taskPointer.centroid.scenePosition.x,taskPointer.centroid.scenePosition.y])")
        centroid_before, _ = centroid_expression.evaluate()
        assert not centroid_expression.hasError(), centroid_expression.error().toString()
        move(reentry)
        centroid_after, _ = centroid_expression.evaluate()
        assert not centroid_expression.hasError(), centroid_expression.error().toString()
        assert json.loads(centroid_after) != json.loads(centroid_before), "event_arrival_reentry_motion_not_delivered"
        result["viewportInProgress"].update(reentryPoint=[reentry.x(), reentry.y()],
            centroidBeforeReentry=json.loads(centroid_before), centroidAfterReentry=json.loads(centroid_after))
        assert not evaluate("taskDrag.pressed") and not marker.isVisible(), "event_arrival_clear_rearmed_gesture"
        assert_no_model_mutation(structural)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, reentry)
        held = False
        QTest.qWait(100)
        assert snapshot() == before and saved() == raw and evaluate("JSON.stringify(taskOrder())") == full_raw, "event_arrival_release_mutation"
        assert writes.count() == legacy_writes.count() == 0 and all(spy.count() == 0 for spy in clicks), "event_arrival_release_write_or_click"
        assert_no_model_mutation(structural)
        assert not evaluate("taskDrag.pressed") and not marker.isVisible(), "event_arrival_terminal_ticket_or_marker"
        assert event_eval("current === null && pending.length === 0 && sequence === " + str(event_fact["sequence"])), "event_arrival_release_changed_cleared_state"
        result["viewportCases"].append({**result["viewportInProgress"], "profilesSetterSignals": writes.count(),
                                        "clickedSignals": 0, "canceledBeforeFurtherMotion": True,
                                        "fullOrderUnchanged": True, "savedUnchanged": True,
                                        "submittedEvent": event_fact, "eventIntentionallyCleared": True})
        result.pop("viewportInProgress")
        record("viewport-event-arrival-canceled-without-rearm")
    finally:
        if held:
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, last)
            QTest.qWait(20)
