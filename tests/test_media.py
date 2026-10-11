import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, Property, Signal, Slot, QAbstractListModel, QModelIndex, QUrl, Qt, QPointF
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


class FixturePlayer(QObject):
    changed = Signal()

    def __init__(self, identity="Spotify", desktop="spotify", **values):
        super().__init__()
        self.values = dict(identity=identity, desktopEntry=desktop, track="Faixa sintética", artist="Artista sintético",
                           canControl=True, canPlay=True, canPause=True, canGoPrevious=True, canGoNext=True,
                           playbackStatus=3)
        self.values.update(values)
        self.calls = []

    def update(self, **values):
        self.values.update(values)
        self.changed.emit()

    identity = Property(str, lambda self: self.values["identity"], notify=changed)
    desktopEntry = Property(str, lambda self: self.values["desktopEntry"], notify=changed)
    track = Property(str, lambda self: self.values["track"], notify=changed)
    artist = Property(str, lambda self: self.values["artist"], notify=changed)
    canControl = Property(bool, lambda self: self.values["canControl"], notify=changed)
    canPlay = Property(bool, lambda self: self.values["canPlay"], notify=changed)
    canPause = Property(bool, lambda self: self.values["canPause"], notify=changed)
    canGoPrevious = Property(bool, lambda self: self.values["canGoPrevious"], notify=changed)
    canGoNext = Property(bool, lambda self: self.values["canGoNext"], notify=changed)
    playbackStatus = Property(int, lambda self: self.values["playbackStatus"], notify=changed)

    @Slot()
    def Play(self):
        self.calls.append("Play")

    @Slot()
    def Pause(self):
        self.calls.append("Pause")

    @Slot()
    def Previous(self):
        self.calls.append("Previous")

    @Slot()
    def Next(self):
        self.calls.append("Next")


class FixtureMedia(QAbstractListModel):
    currentIndexChanged = Signal()
    currentPlayerChanged = Signal()
    roles = {Qt.UserRole + 1: b"identity", Qt.UserRole + 2: b"desktopEntry",
             Qt.UserRole + 3: b"isMultiplexer", Qt.UserRole + 4: b"container"}

    def __init__(self):
        super().__init__()
        self.players = []
        self._index = 0
        self.player_override = None

    def roleNames(self):
        return self.roles

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.players)

    def data(self, index, role):
        if not index.isValid() or index.row() >= len(self.players):
            return None
        player = self.players[index.row()]
        role_name = self.roles.get(role)
        if role_name == b"container":
            return player
        if role_name == b"isMultiplexer":
            return index.row() == 0
        if role_name:
            return player.values[role_name.decode()]
        return None

    def replace(self, players):
        self.beginResetModel()
        self.players = players
        self._index = 0
        self.endResetModel()
        self.currentIndexChanged.emit()
        self.currentPlayerChanged.emit()

    def set_index(self, index):
        if not self.players:
            self._index = 0
        else:
            self._index = max(0, min(index, len(self.players) - 1))
        self.currentIndexChanged.emit()
        self.currentPlayerChanged.emit()

    currentIndex = Property(int, lambda self: self._index, set_index, notify=currentIndexChanged)
    currentPlayer = Property("QVariant", lambda self: self.player_override or (self.players[self._index] if self.players else None),
                             notify=currentPlayerChanged)


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.media = FixtureMedia()
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda warnings: self.warnings.extend(w.toString() for w in warnings))
        self.engine.rootContext().setContextProperty("fixtureMedia", self.media)
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("MediaHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.controls = self.window.findChild(QQuickItem, "mediaUnderTest")
        QTest.qWait(40)

    def tearDown(self):
        if self.engine.rootObjects():
            self.window.close()
        self.engine.deleteLater()
        self.app.processEvents()

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.controls, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def item(self, name):
        item = self.window.findChild(QQuickItem, name)
        self.assertIsNotNone(item, name)
        return item

    def populate(self, **values):
        self.player = FixturePlayer(**values)
        self.media.replace([self.player, self.player])
        QTest.qWait(30)
        return self.player

    def test_empty_state_and_no_actions(self):
        self.assertTrue(self.item("mediaEmptyState").property("visible"))
        self.assertFalse(self.item("mediaPlayPause").property("enabled"))
        self.assertFalse(self.evaluate("mediaState.playPause()"))
        self.assertEqual(self.warnings, [])

    def test_spotify_is_preferred_and_keyboard_can_choose_another_player(self):
        other = FixturePlayer(identity="VLC", desktop="vlc")
        spotify = FixturePlayer()
        self.media.replace([other, other, spotify])
        QTest.qWait(40)
        self.assertEqual(self.media._index, 2)
        chooser = self.item("mediaPlayerChooser")
        self.assertEqual(chooser.property("currentText"), "Spotify")
        self.evaluate("forceActiveFocus()", chooser)
        QTest.keyClick(self.window, Qt.Key_Up)
        QTest.qWait(20)
        self.assertEqual(self.media.currentPlayer, other)
        self.assertEqual(chooser.property("currentText"), "VLC")
        other.calls.clear()
        self.assertTrue(self.evaluate("mediaState.playPause()"))
        self.assertEqual(other.calls, ["Play"])
        self.assertEqual(spotify.calls, [])
        self.assertEqual(self.warnings, [])

    def test_pause_and_play_respect_the_current_capability(self):
        player = self.populate(playbackStatus=2, canPlay=False, canPause=True)
        button = self.item("mediaPlayPause")
        self.assertEqual(button.property("text"), "Pausar")
        self.assertTrue(button.property("enabled"))
        self.evaluate("forceActiveFocus()", button)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertEqual(player.calls, ["Pause"])
        player.update(playbackStatus=3)
        self.assertFalse(button.property("enabled"))
        self.assertFalse(self.evaluate("mediaState.playPause()"))
        player.update(canPlay=True, canPause=False)
        self.assertTrue(button.property("enabled"))
        self.assertTrue(self.evaluate("mediaState.playPause()"))
        self.assertEqual(player.calls, ["Pause", "Play"])
        player.update(canControl=False)
        self.assertFalse(self.evaluate("mediaState.previous()"))
        self.assertFalse(self.evaluate("mediaState.next()"))
        self.assertFalse(self.evaluate("mediaState.playPause()"))
        self.assertEqual(player.calls, ["Pause", "Play"])
        self.assertEqual(self.warnings, [])

    def test_unknown_status_and_player_disappearance_disable_commands(self):
        player = self.populate(playbackStatus=0)
        self.assertFalse(self.item("mediaPlayPause").property("enabled"))
        self.assertIn("indisponível", self.item("mediaPlaybackState").property("text").lower())
        self.media.replace([])
        QTest.qWait(30)
        self.assertTrue(self.item("mediaEmptyState").property("visible"))
        self.assertFalse(self.evaluate("mediaState.previous()"))
        self.assertFalse(self.evaluate("mediaState.next()"))
        self.assertFalse(self.evaluate("mediaState.playPause()"))
        self.assertEqual(player.calls, [])
        self.assertEqual(self.warnings, [])

    def test_command_failure_is_visible_and_clears_with_another_player(self):
        self.populate()
        self.media.player_override = self.engine.evaluate("({ identity: 'Player sintético', track: 'Faixa', artist: 'Artista', canControl: true, canPlay: true, canPause: true, canGoPrevious: true, canGoNext: true, playbackStatus: 3, Next: function() { throw new Error('synthetic receiver unavailable'); } })")
        self.media.currentPlayerChanged.emit()
        self.assertFalse(self.evaluate("mediaState.next()"))
        error = self.item("mediaActionError")
        self.assertTrue(error.property("visible"))
        self.assertIn("Tente novamente", error.property("text"))
        self.assertNotIn("synthetic receiver", error.property("text"))
        self.media.player_override = None
        self.media.currentPlayerChanged.emit()
        self.assertFalse(error.property("visible"))
        self.assertEqual(self.warnings, [])

    def test_previous_next_and_dynamic_capability_revocation(self):
        player = self.populate(canGoPrevious=False, canGoNext=True)
        self.assertFalse(self.item("mediaPrevious").property("enabled"))
        self.assertFalse(self.evaluate("mediaState.previous()"))
        self.assertTrue(self.evaluate("mediaState.next()"))
        player.update(canGoPrevious=True, canGoNext=False)
        self.assertTrue(self.evaluate("mediaState.previous()"))
        self.assertFalse(self.item("mediaNext").property("enabled"))
        self.assertFalse(self.evaluate("mediaState.next()"))
        self.assertEqual(player.calls, ["Next", "Previous"])
        self.assertEqual(self.warnings, [])

    def test_metadata_is_plain_bounded_and_scrollable_in_small_windows(self):
        self.populate(track="<b>" + "X" * 5000, artist="<i>" + "Y" * 5000)
        self.window.setWidth(250)
        self.window.setHeight(140)
        QTest.qWait(30)
        for name in ("mediaTrack", "mediaArtist"):
            label = self.item(name)
            self.assertEqual(self.evaluate("textFormat", label), 0)
            self.assertLessEqual(len(label.property("text")), 512)
            self.assertLessEqual(label.width(), self.controls.width())
        scroll = self.item("mediaScroll")
        self.assertGreater(scroll.property("contentHeight"), scroll.height())
        self.assertEqual(self.warnings, [])

    def test_backend_unavailable_has_a_clear_empty_state(self):
        self.evaluate("media = null")
        self.assertIn("indisponíveis", self.item("mediaEmptyState").property("text"))
        self.assertFalse(self.evaluate("mediaState.playPause()"))
        self.assertEqual(self.warnings, [])

    def test_player_disappearance_recovers_keyboard_focus(self):
        self.populate()
        button = self.item("mediaPlayPause")
        self.evaluate("forceActiveFocus()", button)
        self.assertTrue(button.property("activeFocus"))
        self.media.replace([])
        QTest.qWait(40)
        self.assertFalse(button.property("activeFocus"))
        self.assertTrue(self.controls.property("activeFocus"))
        self.assertEqual(self.warnings, [])

    def test_manual_selection_is_preserved_when_spotify_appears(self):
        other = FixturePlayer(identity="VLC", desktop="vlc")
        self.media.replace([other, other])
        QTest.qWait(30)
        self.evaluate("mediaState.choosePlayer(1)")
        self.media.beginInsertRows(QModelIndex(), 2, 2)
        self.media.players.append(FixturePlayer())
        self.media.endInsertRows()
        QTest.qWait(30)
        self.assertEqual(self.media._index, 1)
        self.assertEqual(self.item("mediaPlayerChooser").property("currentText"), "VLC")
        self.assertEqual(self.warnings, [])

    def test_compact_tab_navigation_keeps_each_focused_control_inside_the_viewport(self):
        self.populate(track="<b>" + "X" * 5000, artist="<i>" + "Y" * 5000)
        self.window.setWidth(250)
        self.window.setHeight(140)
        QTest.qWait(40)
        viewport = self.item("mediaScroll").property("contentItem")
        # Enter through actual Tab navigation rather than assigning focus to a button.
        for _ in range(8):
            QTest.keyClick(self.window, Qt.Key_Tab)
            QTest.qWait(10)
            if self.window.activeFocusItem().objectName() == "mediaPlayerChooser":
                break
        self.assertEqual(self.window.activeFocusItem().objectName(), "mediaPlayerChooser")
        for name in ("mediaPrevious", "mediaPlayPause", "mediaNext"):
            QTest.keyClick(self.window, Qt.Key_Tab)
            QTest.qWait(10)
            control = self.item(name)
            self.assertEqual(self.window.activeFocusItem(), control)
            top_left = control.mapToItem(viewport, QPointF(0, 0))
            self.assertGreaterEqual(top_left.x(), -0.5, name)
            self.assertGreaterEqual(top_left.y(), -0.5, name)
            self.assertLessEqual(top_left.x() + control.width(), viewport.width() + 0.5, name)
            self.assertLessEqual(top_left.y() + control.height(), viewport.height() + 0.5, name)
        for name in ("mediaPlayPause", "mediaPrevious", "mediaPlayerChooser"):
            QTest.keyClick(self.window, Qt.Key_Tab, Qt.ShiftModifier)
            QTest.qWait(10)
            control = self.item(name)
            self.assertEqual(self.window.activeFocusItem(), control)
            top_left = control.mapToItem(viewport, QPointF(0, 0))
            self.assertGreaterEqual(top_left.y(), -0.5, name)
            self.assertLessEqual(top_left.y() + control.height(), viewport.height() + 0.5, name)
        self.assertEqual(self.warnings, [])

    def test_selector_popup_delegates_are_created_and_render_plain_text(self):
        other = FixturePlayer(identity="<b>VLC</b>", desktop="vlc")
        spotify = FixturePlayer()
        self.media.replace([other, other, spotify])
        QTest.qWait(30)
        chooser = self.item("mediaPlayerChooser")
        self.evaluate("mediaState.choosePlayer(1)")
        self.assertEqual(self.evaluate("contentItem.text", chooser), "<b>VLC</b>")
        self.assertTrue(self.evaluate("typeof contentItem.positionToRectangle === 'function'", chooser))
        self.evaluate("popup.open(); popup.contentItem.forceLayout()", chooser)
        QTest.qWait(50)
        self.assertEqual(self.evaluate("popup.contentItem.count", chooser), 3)
        self.assertEqual(self.evaluate("popup.contentItem.itemAtIndex(1).contentItem.text", chooser), "<b>VLC</b>")
        self.assertEqual(self.evaluate("popup.contentItem.itemAtIndex(1).contentItem.textFormat", chooser), 0)
        self.evaluate("popup.close()", chooser)
        self.assertEqual(self.warnings, [])


if __name__ == "__main__":
    unittest.main()
