"""One stable-overflow drag through real Qt pointer events on the owned fixture."""
import json
import time
from PySide6.QtCore import QPoint, QPointF, Qt
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
        return evaluate("JSON.stringify(Array.from(profiles.effective.launchers))")
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
        expected_saved = json.loads(raw)
        source_url = "applications:" + source["id"] + ".desktop"
        target_url = "applications:" + target["id"] + ".desktop"
        expected_saved.remove(source_url)
        expected_saved.insert(expected_saved.index(target_url) + 1, source_url)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, destination)
        held = False
        settle(lambda: [row["id"] for row in snapshot()["rows"]] == expected_ids)
        QTest.qWait(100)
        after = snapshot()
        assert after["foreignRowCount"] == foreign_count and after["foreignLauncherCount"] == 0, "viewport_foreign_count_after_release"
        after_full = json.loads(evaluate("JSON.stringify(taskOrder())"))
        assert [row["identity"] for row in after_full] == expected_full_ids, "viewport_full_identity_splice_wrong"
        assert {row["id"]: row["WinIdList"] for row in after["rows"]} == {row["id"]: row["WinIdList"] for row in before["rows"]}, "viewport_window_identity_changed"
        assert after["launcherList"] == expected_saved and json.loads(saved()) == expected_saved, "viewport_saved_splice_wrong"
        assert writes.count() == 1 and legacy_writes.count() == 0 and all(spy.count() == 0 for spy in clicks), "viewport_release_write_or_click"
        assert not evaluate("taskDrag.pressed") and not marker.isVisible(), "viewport_terminal_ticket_or_marker"
        result["viewportCase"] = {"case": "stable-overflow-valid-release", "beforeOrder": before_ids,
            "afterOrder": expected_ids, "source": source["id"], "target": target["id"],
            "foreignRowCount": foreign_count, "fullBeforeOrder": full_ids, "fullAfterOrder": expected_full_ids,
            "geometryBefore": before_geometry, "profilesSetterSignals": writes.count(), "clickedSignals": 0}
        record("viewport-stable-overflow-release")
    finally:
        if held:
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, last)
            QTest.qWait(20)
