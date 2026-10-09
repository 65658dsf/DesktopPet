"""Regression checks for reopening chat; never reads or writes user settings.

Run with .venv/Scripts/python.exe tools/verify_window_activation.py.
The default Qt platform is offscreen. Set QT_QPA_PLATFORM=windows to repeat
against native Windows windows. IPC uses a unique, test-only server name.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QSharedMemory, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon  # noqa: E402

import config  # noqa: E402
import main as pet_main  # noqa: E402
from window_activation import ActivationServer  # noqa: E402


class FakeConfig:
    """Use independent in-memory defaults, with no filesystem access."""

    def __init__(self) -> None:
        self.data = copy.deepcopy(config.DEFAULTS)
        self.data.update(showOnStartup=False, idleVariety=False)
        self.save_calls = 0

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value

    def save(self) -> None:
        self.save_calls += 1

    @property
    def ai(self):
        return self.data["ai"]


class SelectChatMenu(QMenu):
    """Exercise the controller's actual menu action without a modal popup."""

    def exec(self, _position):
        action = next(action for action in self.actions()
                      if action.text() == "打开对话")
        action.trigger()
        return action


class WindowActivationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        # Do not scan personal pet folders, show a tray icon, or touch autorun.
        for replacement in (
            patch.object(pet_main, "Config", FakeConfig),
            patch.object(pet_main, "scan_packages", return_value=[]),
            patch.object(pet_main.PetApp, "_sync_autostart"),
            patch.object(pet_main.PetApp, "_say"),
            patch.object(pet_main.Tray, "show"),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)
        self.controller = pet_main.PetApp(self.app, QSharedMemory())
        self.chat = self.controller.chat
        self.chat.add_message("user", "Keep this message while reopening.")
        self.message = self.chat.messages.itemAt(0).widget()

    def tearDown(self) -> None:
        # Deliberately avoid PetApp.quit() and main()'s persistence hooks.
        self.assertEqual(self.controller.config.save_calls, 0)
        for timer in self.controller.findChildren(pet_main.QTimer):
            timer.stop()
        self.controller.tray.hide()
        for window in (self.controller.pet, self.controller.bubble,
                       self.controller.chat, self.controller.settings):
            window.hide()
            window.deleteLater()
        self.controller.deleteLater()
        self.app.processEvents()

    def assert_chat_restored(self) -> None:
        self.app.processEvents()
        self.assertIs(self.controller.chat, self.chat)
        self.assertTrue(self.chat.isVisible())
        self.assertFalse(self.chat.isMinimized())
        self.assertIs(self.chat.messages.itemAt(0).widget(), self.message)
        self.assertEqual(self.message.label.text(), "Keep this message while reopening.")

    def prepare_chat(self, state: str) -> None:
        self.chat.showNormal()
        if "minimized" in state:
            self.chat.showMinimized()
        if "hidden" in state:
            self.chat.hide()
        self.app.processEvents()
        if "minimized" in state:
            self.assertTrue(self.chat.isMinimized())
        if "hidden" in state:
            self.assertFalse(self.chat.isVisible())

    def open_context_menu(self) -> None:
        with patch.object(pet_main, "QMenu", SelectChatMenu):
            self.controller.pet.right_clicked.emit(QPoint(10, 10))

    def test_chat_entry_points_restore_same_window(self) -> None:
        tray_action = next(action for action in self.controller.tray.contextMenu().actions()
                           if action.text() == "打开对话")
        entries = {
            "direct": self.controller.open_chat,
            "pet double click signal": self.controller.pet.double_clicked.emit,
            "tray click": lambda: self.controller.tray._on_activated(
                QSystemTrayIcon.ActivationReason.Trigger),
            "tray menu": tray_action.trigger,
            "pet context menu": self.open_context_menu,
        }
        for name, activate in entries.items():
            for state in ("hidden", "minimized", "hidden-minimized"):
                with self.subTest(entry=name, state=state):
                    self.prepare_chat(state)
                    activate()
                    self.assert_chat_restored()

    def test_actual_pet_double_click_event(self) -> None:
        self.prepare_chat("hidden-minimized")
        self.controller.pet.show()
        QTest.mouseDClick(self.controller.pet, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, QPoint(96, 104))
        self.assert_chat_restored()

    def test_maximized_chat_stays_maximized(self) -> None:
        self.chat.showMaximized()
        self.app.processEvents()
        self.assertTrue(self.chat.isMaximized())
        self.chat.showMinimized()
        self.app.processEvents()
        self.assertTrue(self.chat.isMinimized())
        self.controller.open_chat()
        self.assert_chat_restored()
        self.assertTrue(self.chat.isMaximized())

    def test_offscreen_chat_returns_to_available_screen(self) -> None:
        self.chat.showNormal()
        self.chat.move(-100000, -100000)
        self.app.processEvents()
        self.assertFalse(any(screen.availableGeometry().contains(self.chat.frameGeometry().center())
                             for screen in self.app.screens()))
        self.chat.hide()
        self.controller.open_chat()
        self.assert_chat_restored()
        frame = self.chat.frameGeometry()
        self.assertTrue(any(screen.availableGeometry().contains(frame.center())
                            for screen in self.app.screens()))
        self.assertTrue(any(screen.availableGeometry().contains(frame.topLeft())
                            for screen in self.app.screens()))

    def test_settings_restores_after_minimize_and_hide(self) -> None:
        settings = self.controller.settings
        settings.showMinimized()
        settings.hide()
        self.app.processEvents()
        self.assertTrue(settings.isMinimized())
        self.controller.open_settings()
        self.app.processEvents()
        self.assertTrue(settings.isVisible())
        self.assertFalse(settings.isMinimized())

    def test_second_process_ipc_restores_existing_chat(self) -> None:
        name = "qinche-activation-test-" + uuid.uuid4().hex
        listener = ActivationServer(self.app, name)
        listener.chat_requested.connect(self.controller.open_chat)
        requests = []
        listener.chat_requested.connect(lambda: requests.append(True))
        self.addCleanup(listener.server.close)
        self.addCleanup(listener.deleteLater)
        self.prepare_chat("hidden-minimized")
        child_code = (
            "import sys; from PySide6.QtCore import QCoreApplication; "
            "from window_activation import activate_existing_instance; "
            "app = QCoreApplication([]); "
            "sys.exit(0 if activate_existing_instance(sys.argv[1]) else 2)"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "app")
        child = subprocess.Popen(
            [sys.executable, "-c", child_code, name], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and (child.poll() is None or not requests):
                QTest.qWait(10)
            output, errors = child.communicate(timeout=1)
            self.assertEqual(child.returncode, 0, output + errors)
            self.assertEqual(len(requests), 1)
            self.assert_chat_restored()
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
