"""Restore app windows and wake the existing desktop-pet instance."""

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QWidget


ACTIVATION_NAME = "qinche-desktop-pet-open-chat"


def present_window(window: QWidget) -> None:
    # show() alone preserves WindowMinimized, even after the window was hidden.
    # Clear only that flag so a previously maximized window stays maximized.
    window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
    window.show()
    screens = QApplication.screens()
    frame = window.frameGeometry()
    if screens and not any(screen.availableGeometry().contains(frame.center())
                           for screen in screens):
        area = QApplication.primaryScreen().availableGeometry()
        window.move(area.x() + max(0, (area.width() - frame.width()) // 2),
                    area.y() + max(0, (area.height() - frame.height()) // 2))
    window.raise_()
    window.activateWindow()


def activate_existing_instance(name: str = ACTIVATION_NAME) -> bool:
    """A same-user local connection requests the existing chat window."""
    socket = QLocalSocket()
    # The first process may still be starting its listener after taking the lock.
    for _ in range(20):
        socket.connectToServer(name)
        if socket.waitForConnected(100):
            socket.disconnectFromServer()
            return True
        socket.abort()
        QThread.msleep(50)
    return False


class ActivationServer(QObject):
    chat_requested = Signal()

    def __init__(self, parent: QObject, name: str = ACTIVATION_NAME) -> None:
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._on_connection)
        if not self.server.listen(name):
            raise RuntimeError(f"无法创建对话唤醒通道：{self.server.errorString()}")

    def _on_connection(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.close()
            socket.deleteLater()
            self.chat_requested.emit()
