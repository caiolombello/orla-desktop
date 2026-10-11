"""A short-lived owned window for native launch and window-action tests."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication, QColor
from PySide6.QtQuick import QQuickWindow

app = QGuiApplication([])
app.setDesktopFileName("org.caiodock.acceptance")
window = QQuickWindow()
window.setTitle("CaioDock acceptance probe")
window.setFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
window.setWidth(260)
window.setHeight(100)
window.setColor(QColor("#182235"))
window.show()
QTimer.singleShot(15000, app.quit)
app.exec()
