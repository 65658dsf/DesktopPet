"""Drives the real app through its main flows and captures the desktop.

Dev-only harness: shows the pet, triggers a click reaction, a bubble, the chat
window with an offline reply, and the settings panel, capturing the desktop with
Qt (which — unlike a plain BitBlt from PowerShell — includes layered windows).
"""
import sys
from pathlib import Path

APP = Path(r"d:\Coding\DesktopPet\app")
OUT = Path(r"d:\Coding\DesktopPet\tools\gen_pet\out")
sys.path.insert(0, str(APP))

from PySide6.QtCore import QSharedMemory, Qt, QTimer          # noqa: E402
from PySide6.QtWidgets import QApplication, QTabWidget        # noqa: E402

import main as app_main                                       # noqa: E402

QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
app.setApplicationName("秦彻 · 桌面宠物 (verify)")
app.setQuitOnLastWindowClosed(False)

shared = QSharedMemory("qinche-verify-instance")
shared.create(1)

controller = app_main.PetApp(app, shared)
if controller.package is None:
    print("NO PACKAGE FOUND")
    sys.exit(1)
print("package:", controller.package.id, "atlas scale:", controller.renderer.scale)
print("settings file:", controller.config.path)


def shot(name: str) -> None:
    app.primaryScreen().grabWindow(0).save(str(OUT / name))
    print("shot:", name)


def click() -> None:
    controller._on_click()
    print("state after click:", controller.animator.state)


def drag_right() -> None:
    controller._on_drag_move("right")
    print("state while dragging:", controller.animator.state)


def drag_end() -> None:
    controller._on_drag_end()
    print("state after drag:", controller.animator.state)


def open_chat_and_send() -> None:
    controller.open_chat()
    controller._on_send("你好，今天有点累")
    print("chat opened, local reply requested")


def open_settings(tab: int) -> None:
    controller.open_settings()
    tabs = controller.settings.findChild(QTabWidget)
    if tabs is not None:
        tabs.setCurrentIndex(tab)
    print("settings tab:", tab)


sequence = [
    (2500, lambda: shot("v1_pet_idle_bubble.png")),
    (3000, click),
    (3600, lambda: shot("v2_pet_click_reaction.png")),
    (4000, drag_right),
    (4600, lambda: shot("v3_pet_dragging_right.png")),
    (5000, drag_end),
    (5500, open_chat_and_send),
    (7000, lambda: shot("v4_chat_offline_reply.png")),
    (7500, lambda: open_settings(0)),
    (8300, lambda: shot("v5_settings_ai.png")),
    (8700, lambda: open_settings(1)),
    (9500, lambda: shot("v6_settings_look.png")),
    (9900, lambda: open_settings(2)),
    (10700, lambda: shot("v7_settings_behaviour.png")),
    (11000, lambda: print("history:", controller._history)),
    (11200, app.quit),
]
for delay, action in sequence:
    QTimer.singleShot(delay, action)

app.exec()
print("verify done")