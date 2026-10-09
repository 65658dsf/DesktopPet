"""Tray icon + menu, following the launcher contract entries."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class Tray(QSystemTrayIcon):
    toggle_show = Signal()
    open_chat = Signal()
    open_settings = Signal()
    toggle_lock = Signal()
    refresh_pets = Signal()
    quit_requested = Signal()

    def __init__(self, icon: QIcon, pet_name: str) -> None:
        super().__init__(icon)
        self.setToolTip(f"{pet_name} · 桌面宠物")
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #1a1418; color: #f2e7ea; border: 1px solid #43313a;"
            "border-radius: 8px; padding: 6px; }"
            "QMenu::item { padding: 6px 22px; border-radius: 6px; }"
            "QMenu::item:selected { background: #5c1f27; }"
            "QMenu::separator { height: 1px; background: #33262c; margin: 5px 8px; }")

        self.show_action = menu.addAction("隐藏桌宠")
        self.show_action.triggered.connect(self.toggle_show.emit)
        action = menu.addAction("打开对话")
        action.triggered.connect(self.open_chat.emit)
        action = menu.addAction("设置")
        action.triggered.connect(self.open_settings.emit)
        self.lock_action = menu.addAction("锁定位置")
        self.lock_action.triggered.connect(self.toggle_lock.emit)
        menu.addSeparator()
        action = menu.addAction("刷新宠物包")
        action.triggered.connect(self.refresh_pets.emit)
        menu.addSeparator()
        action = menu.addAction("退出")
        action.triggered.connect(self.quit_requested.emit)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_show.emit()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_chat.emit()

    def set_pet_visible(self, visible: bool) -> None:
        self.show_action.setText("隐藏桌宠" if visible else "显示桌宠")

    def set_locked(self, locked: bool) -> None:
        self.lock_action.setText("解锁位置" if locked else "锁定位置")