"""秦彻 · 桌面宠物 — application entry point and controller.

Offline first: animation, interaction, tray, settings and the built-in reply
engine never touch the network. AI chat can optionally use any OpenAI-compatible
endpoint (including local servers such as Ollama), and can be switched off
entirely from the settings panel.
"""

from __future__ import annotations

import datetime
import random
import sys
import threading
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QObject, QPoint, QRect, QSharedMemory, QTimer, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from ai.client import ChatEngine
from ai.local_engine import (bubble_line, local_reply, opening_line, parse_command,
                             summarize_for_bubble)
from animation import Animator
from chat_window import ChatWindow
from config import Config, data_dir
from pet_window import Bubble, PetWindow, SpriteRenderer
from petpack import STATE_ROWS, PetPackage, scan_packages
from settings_window import SettingsWindow
from tray import Tray
from window_activation import ActivationServer, activate_existing_instance, present_window

APP_NAME = "秦彻 · 桌面宠物"
APP_DIR = Path(__file__).resolve().parent
QUIET_STATES = ("chin-rest", "review", "waiting", "waving")
LEGACY_QUIET_STATES = ("review", "waving")
FRAME_PRELOAD_ORDER = ("idle", "poke", "waiting", "running", "running-right",
                       "running-left", "chin-rest", "review", "waving", "jumping", "failed")
POKE_BURST_SECONDS = 2.5


class PetApp(QObject):
    def __init__(self, qapp: QApplication, shared: QSharedMemory) -> None:
        super().__init__()
        self.qapp = qapp
        self._shared = shared                      # keep the single-instance handle alive
        self.config = Config()
        self.packages: list[PetPackage] = []
        self.package: PetPackage | None = None
        self.renderer: SpriteRenderer | None = None
        self._clicks = 0
        self._poke_burst = 0
        self._last_poke_time: float | None = None
        self._poke_queued = False
        self._history: list[dict] = []
        self._expressive_states: set[str] = set()
        self._blink_frames: dict[str, frozenset[int]] = {}
        self._last_idle_action: str | None = None
        self._state_preview_active = False
        self._drag_direction: str | None = None
        self._reply_pending = False
        self._reply_streaming = False

        self.animator = Animator(self)
        self.pet = PetWindow()
        self.bubble = Bubble()
        self.chat = ChatWindow()
        self.llm = ChatEngine(self)

        self.reload_packages(preferred=self.config.get("activePetId"))
        self.settings = SettingsWindow(self.config, self.packages)
        self.tray = Tray(self._icon(), self.package.display_name if self.package else APP_NAME)

        self._wire()
        self._apply_settings(self.config.data, initial=True)

        if self.config.get("showOnStartup", True):
            self.pet.show()
        self.tray.show()
        self._standby()
        QTimer.singleShot(1200, lambda: self._say(opening_line()))

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._idle_variety)
        self._schedule_idle_variety()

    # ------------------------------------------------------------------ #
    # packages & settings
    # ------------------------------------------------------------------ #
    def reload_packages(self, preferred: str | None = None) -> None:
        self.packages = scan_packages(self.config.get("petFolders"))
        target = None
        for package in self.packages:
            if package.id == (preferred or ""):
                target = package
                break
        if target is None and self.packages:
            target = self.packages[0]
        if target is not None:
            self._install_package(target)

    def _install_package(self, package: PetPackage) -> None:
        self.package = package
        size = (int(self.config.get("width", 192)), int(self.config.get("height", 208)))
        self.renderer = SpriteRenderer(package)
        dpr = self.qapp.primaryScreen().devicePixelRatio() if self.qapp.primaryScreen() else 1.0
        from PySide6.QtCore import QSize

        self.renderer.configure(QSize(*size), dpr, bool(self.config.get("pixelated", False)))
        self._configure_clips()
        if self.renderer.atlas is not None:
            self.chat.set_avatar(QPixmap.fromImage(self.renderer.atlas.cell_image("idle", 0)))

    def _configure_clips(self) -> None:
        self._poke_queued = False
        self._state_preview_active = False
        clips = self.renderer.atlas.clip_durations() if self.renderer and self.renderer.atlas else {}
        self._expressive_states = set(clips)
        self._last_idle_action = None
        self._blink_frames = {}
        specs = self.package.manifest.get("animationClips", {}) if self.package else {}
        for state, timings in clips.items():
            spec = specs.get(state, {}) if isinstance(specs, dict) else {}
            # Older expressive packages used these two known blink sequences.
            # Other actions declare their eyelid frames explicitly, so a new
            # review or running pose cannot accidentally inherit blink timing.
            default = (1, 2, 3, 4) if state == "idle" else (2,) if state == "poke" else ()
            frames = spec.get("blinkFrames", default) if isinstance(spec, dict) else default
            if isinstance(frames, (list, tuple)):
                self._blink_frames[state] = frozenset(
                    index for index in frames
                    if type(index) is int and 0 <= index < len(timings))
        if self.renderer is not None:
            order = dict.fromkeys((*FRAME_PRELOAD_ORDER, *clips))
            self.renderer.prepare_frames([state for state in order if state in clips])
        self.animator.set_clips(clips)

    def _icon(self) -> QIcon:
        for name in ("qinche.ico", "icon.ico"):
            path = APP_DIR / "assets" / name
            if path.is_file():
                return QIcon(str(path))
        if self.renderer is not None:
            pixmap = self.renderer.pixmap("idle", 0)
            if not pixmap.isNull():
                return QIcon(pixmap)
        return QIcon()

    def _wire(self) -> None:
        self.animator.frame_changed.connect(self._on_frame)
        self.animator.finished.connect(self._on_animation_finished)

        self.pet.clicked.connect(self._on_click)
        self.pet.double_clicked.connect(self.open_chat)
        self.pet.right_clicked.connect(self._on_context_menu)
        self.pet.drag_moved.connect(self._on_drag_move)
        self.pet.drag_finished.connect(self._on_drag_end)
        self.pet.moved.connect(self._on_pet_moved)

        self.chat.send_requested.connect(self._on_send)
        self.chat.stop_requested.connect(self.llm.cancel)
        self.chat.clear_requested.connect(self._clear_chat)
        self.chat.settings_requested.connect(self.open_settings)

        self.llm.started.connect(lambda: None)
        self.llm.delta.connect(self._on_llm_delta)
        self.llm.done.connect(self._on_llm_done)
        self.llm.error.connect(self._on_llm_error)

        self.settings.apply_requested.connect(self._on_settings_applied)
        self.settings.open_folder_requested.connect(
            lambda: self._open_folder(data_dir()))
        self.settings.reset_position_requested.connect(self._reset_position)
        self.settings.state_preview_requested.connect(self._on_state_preview)

        self.tray.toggle_show.connect(self._toggle_visible)
        self.tray.open_chat.connect(self.open_chat)
        self.tray.open_settings.connect(self.open_settings)
        self.tray.toggle_lock.connect(self._toggle_lock)
        self.tray.refresh_pets.connect(self._on_refresh_pets)
        self.tray.quit_requested.connect(self.quit)

    # ------------------------------------------------------------------ #
    # animation helpers
    # ------------------------------------------------------------------ #
    def _on_frame(self, state: str, index: int) -> None:
        if self.renderer is None:
            return
        self.pet.set_motion_enabled(not self.animator.paused
                                    and state in ("idle", "chin-rest", "review", "waiting", "poke"))
        remaining = self.animator.transition_duration_ms()
        # Eyelids must still visibly close; use only a brief transition during
        # blinks. Arm gestures and changes of state get a little more easing.
        blinking = index in self._blink_frames.get(state, ())
        ceiling = 35 if blinking else 70
        transition_ms = min(ceiling, int(remaining * 0.75))
        self.pet.set_frame(self.renderer.pixmap(state, index), transition_ms=transition_ms)

    def _standby(self) -> None:
        self._poke_queued = False
        self._state_preview_active = False
        if self._drag_direction is not None:
            self.animator.play(f"running-{self._drag_direction}")
            return
        if self._reply_pending:
            self.animator.play("running" if self._reply_streaming else "waiting")
            return
        state = str(self.config.get("manualState", "auto"))
        if state in ("auto", "idle") or state not in STATE_ROWS:
            self.animator.play("idle")
        else:
            self.animator.play(state)
        if hasattr(self, "_idle_timer"):
            self._schedule_idle_variety()

    def _on_animation_finished(self, state: str) -> None:
        self._state_preview_active = False
        replay = state == "poke" and self._poke_queued
        self._poke_queued = False
        if replay and "poke" in self._expressive_states and self._can_animate_poke():
            self.animator.play("poke", loop=False)
        else:
            self._standby()

    def _on_state_preview(self, state: str) -> None:
        self._poke_queued = False
        if self._drag_direction is not None or self._reply_pending:
            self._standby()
        elif state in STATE_ROWS:
            self._state_preview_active = True
            self.animator.play(state, loop=False, cycles=2)
        else:
            self._standby()

    def _schedule_idle_variety(self) -> None:
        interval = ((14000, 30000) if any(state in self._expressive_states for state in QUIET_STATES)
                    else (18000, 42000))
        self._idle_timer.start(random.randint(*interval))

    def _idle_variety(self) -> None:
        if (self.config.get("idleVariety", True)
                and not self.config.get("reducedMotion", False)
                and not self.animator.paused
                and str(self.config.get("manualState", "auto")) == "auto"
                and not self._state_preview_active
                and self._drag_direction is None
                and not self._reply_pending
                and not self.llm.busy
                and self.animator.state in ("idle",)
                and self.pet.isVisible()):
            if "idle" in self._expressive_states and self.animator.frame != 0:
                # Finish reopening the eyes before moving into a larger pose.
                self._idle_timer.start(250)
                return
            candidates = [state for state in QUIET_STATES if state in self._expressive_states]
            if not candidates:
                candidates = list(LEGACY_QUIET_STATES)
            if len(candidates) > 1 and self._last_idle_action in candidates:
                candidates.remove(self._last_idle_action)
            state = random.choice(candidates)
            self._last_idle_action = state
            self.animator.play(state, loop=False)
        self._schedule_idle_variety()

    # ------------------------------------------------------------------ #
    # pet interaction
    # ------------------------------------------------------------------ #
    def _can_animate_poke(self) -> bool:
        return (self.pet.isVisible()
                and self._drag_direction is None
                and not self._reply_pending
                and not self.llm.busy
                and not self.animator.paused
                and not self.config.get("reducedMotion", False))

    def _on_click(self) -> None:
        self._clicks += 1
        now = monotonic()
        if self._last_poke_time is None or now - self._last_poke_time > POKE_BURST_SECONDS:
            self._poke_burst = 1
        else:
            self._poke_burst += 1
        self._last_poke_time = now
        kind = "poke_soft" if self._poke_burst == 1 else "poke" if self._poke_burst == 2 else "poke_repeat"
        self._say(bubble_line(kind))
        if not self._can_animate_poke():
            self._poke_queued = False
            return
        self._state_preview_active = False
        if "poke" in self._expressive_states:
            if self.animator.state == "poke" and self.animator.playing:
                # A fresh click still gets speech immediately. Finish the
                # current reaction before at most one queued replay, so rapid
                # clicks cannot pin the character to the first pose.
                self._poke_queued = True
            else:
                self._poke_queued = False
                self.animator.play("poke", loop=False)
            return
        if self._clicks % 5 == 0:
            self.animator.play("jumping", loop=False)
        else:
            self.animator.play("waving", loop=False, cycles=random.choice([1, 2]))

    def _on_drag_move(self, direction: str) -> None:
        self._poke_queued = False
        self._state_preview_active = False
        self._drag_direction = direction
        self.animator.play(f"running-{direction}", loop=True)

    def _on_drag_end(self) -> None:
        self._drag_direction = None
        self._standby()
        if random.random() < 0.45:
            self._say(bubble_line("drag"))
        self.config.data["x"] = self.pet.x()
        self.config.data["y"] = self.pet.y()
        self.config.save()

    def _on_pet_moved(self, _pos: QPoint) -> None:
        if self.bubble.isVisible():
            self.bubble.place(self.pet.frameGeometry())

    def _say(self, text: str, seconds: float | None = None) -> None:
        if not text or not self.pet.isVisible():
            return
        self.bubble.show_text(
            text,
            seconds or float(self.config.get("chat", {}).get("bubbleSeconds", 6)),
            anchor=self.pet.frameGeometry())

    def _toggle_visible(self) -> None:
        if self.pet.isVisible():
            self._poke_queued = False
            self.pet.hide()
            self.bubble.hide()
        else:
            self.pet.show()
            self.pet.raise_()
            self._say(bubble_line("hide"))
        self.tray.set_pet_visible(self.pet.isVisible())

    def _toggle_lock(self) -> None:
        locked = not bool(self.config.get("locked", False))
        self.config.set("locked", locked)
        self.pet.set_locked(locked)
        self.tray.set_locked(locked)
        self.settings.reload()
        self._say("锁好了，别乱动。" if locked else "解锁了，随你。")

    def _on_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #1a1418; color: #f2e7ea; border: 1px solid #43313a;"
            "border-radius: 8px; padding: 6px; }"
            "QMenu::item { padding: 6px 22px; border-radius: 6px; }"
            "QMenu::item:selected { background: #5c1f27; }"
            "QMenu::separator { height: 1px; background: #33262c; margin: 5px 8px; }")
        menu.addAction("打开对话", self.open_chat)
        menu.addAction("设置", self.open_settings)
        menu.addSeparator()
        locked = bool(self.config.get("locked", False))
        menu.addAction("解锁位置" if locked else "锁定位置", self._toggle_lock)
        menu.addAction("忽略鼠标" + ("（已开启）" if self.config.get("clickThrough") else ""),
                       lambda: self._quick_toggle("clickThrough"))
        menu.addAction("置顶" + ("（已开启）" if self.config.get("alwaysOnTop") else ""),
                       lambda: self._quick_toggle("alwaysOnTop"))
        menu.addSeparator()
        menu.addAction("隐藏" if self.pet.isVisible() else "显示", self._toggle_visible)
        menu.addAction("退出", self.quit)
        menu.exec(global_pos)

    def _quick_toggle(self, key: str) -> None:
        value = not bool(self.config.get(key, False))
        self.config.set(key, value)
        self._apply_settings(self.config.data)
        self.settings.reload()

    def _reset_position(self) -> None:
        self._move_to_default_position()
        self.config.data["x"] = self.pet.x()
        self.config.data["y"] = self.pet.y()
        self.config.save()

    def _move_to_default_position(self) -> None:
        screen = self.pet.screen() or self.qapp.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.pet.move(area.right() - self.pet.width() - 48,
                      area.bottom() - self.pet.height() - 96)

    # ------------------------------------------------------------------ #
    # chat
    # ------------------------------------------------------------------ #
    def open_chat(self) -> None:
        self._poke_queued = False
        if self.animator.state == "poke":
            self._standby()
        if not self.pet.isVisible():
            self.pet.show()
            self.tray.set_pet_visible(True)
        present_window(self.chat)

    def open_settings(self) -> None:
        self.settings.reload()
        present_window(self.settings)

    def _clear_chat(self) -> None:
        self._history.clear()
        self.chat.clear_messages()
        self._say("都清掉了。")

    def _on_send(self, text: str) -> None:
        self._poke_queued = False
        self.chat.add_message("user", text)
        command = parse_command(text)
        if command:
            self._run_command(command)
            return

        self._history.append({"role": "user", "content": text})
        limit = int(self.config.ai.get("historyLimit", 100))
        self._history = self._history[-limit:]

        ai = self.config.ai
        online = ai.get("mode") == "online" and bool(str(ai.get("baseUrl", "")).strip())
        self._reply_pending = True
        self._reply_streaming = False
        if online:
            self._say(bubble_line("thinking"), 3)
            self._standby()
            self.chat.begin_stream()
            messages = [{"role": "system", "content": str(ai.get("systemPrompt", ""))}]
            messages += [dict(item) for item in self._history]
            self.llm.send(messages, ai)
        else:
            self.chat.set_busy(True, "……")
            self._standby()
            QTimer.singleShot(random.randint(500, 1200), lambda: self._local_answer(text))

    def _local_answer(self, text: str) -> None:
        answer = local_reply(text)
        self._reply_pending = False
        self._reply_streaming = False
        self.chat.set_busy(False)
        self.chat.add_message("assistant", answer)
        self._history.append({"role": "assistant", "content": answer})
        self._say(summarize_for_bubble(answer))
        self._standby()

    def _on_llm_delta(self, piece: str) -> None:
        if not piece:
            return
        self.chat.append_delta(piece)
        if self._reply_pending and not self._reply_streaming:
            # Change only on the first content chunk. Restarting on each token
            # would strand the working gesture on frame zero during a stream.
            self._reply_streaming = True
            self._standby()

    def _on_llm_done(self, _text: str) -> None:
        self._reply_pending = False
        self._reply_streaming = False
        text = self.chat.finish_stream()
        if text:
            self._history.append({"role": "assistant", "content": text})
            self._say(summarize_for_bubble(text))
        self._standby()

    def _on_llm_error(self, message: str) -> None:
        self._reply_pending = False
        self._reply_streaming = False
        self.chat.show_error(message)
        if self._drag_direction is not None or self.animator.paused:
            self._standby()
        else:
            self.animator.play("failed", loop=False, cycles=2)
        self._say(bubble_line("error"))

    def _run_command(self, command: str) -> None:
        now = datetime.datetime.now()
        weekday = "一二三四五六日"
        answers = {
            "time": f"现在 {now:%H:%M}。",
            "date": f"{now:%Y-%m-%d}，星期{weekday[now.weekday()]}。",
            "status": (f"当前宠物包：{self.package.id if self.package else '无'}；"
                       f"模式：{'在线 AI' if self.config.ai.get('mode') == 'online' else '本地离线'}；"
                       f"动画状态：{self.animator.state}。"),
        }
        if command in answers:
            self.chat.add_message("assistant", answers[command])
            self._say(summarize_for_bubble(answers[command]))
            return
        if command == "hide":
            self.pet.hide()
            self.tray.set_pet_visible(False)
        elif command == "show":
            self.pet.show()
            self.tray.set_pet_visible(True)
            self.open_chat()
        elif command == "settings":
            self.open_settings()
        elif command == "chat":
            self.open_chat()
        elif command == "clear":
            self._clear_chat()
        elif command == "quit":
            self.quit()

    # ------------------------------------------------------------------ #
    # settings
    # ------------------------------------------------------------------ #
    def _on_settings_applied(self, values: dict) -> None:
        package_changed = str(values.get("activePetId")) != str(self.config.get("activePetId"))
        self.config.data.update(values)
        self.config.save()
        self._apply_settings(self.config.data, package_changed=package_changed)
        self.settings.reload()

    def _apply_settings(self, values: dict, initial: bool = False,
                        package_changed: bool = False) -> None:
        self.pet.set_transitions_enabled(not bool(values.get("reducedMotion", False)))
        if package_changed or self.renderer is None:
            self.reload_packages(preferred=str(values.get("activePetId", "")))
            if self.package is not None:
                self.tray.setToolTip(f"{self.package.display_name} · 桌面宠物")

        width = max(96, int(values.get("width", 192)))
        height = max(104, int(values.get("height", 208)))
        if (self.pet.width(), self.pet.height()) != (width, height):
            anchor = self.pet.frameGeometry().center()
            self.pet.resize(width, height)
            self.pet.move(anchor.x() - width // 2, anchor.y() - height // 2)
        self.bubble.hide()

        self.pet.drag_enabled = bool(values.get("dragEnabled", True))
        self.pet.set_locked(bool(values.get("locked", False)))
        self.pet.set_click_through(bool(values.get("clickThrough", False)))
        if initial or bool(values.get("alwaysOnTop", True)) != bool(
                self.pet.windowFlags() & Qt.WindowType.WindowStaysOnTopHint):
            self.pet.set_always_on_top(bool(values.get("alwaysOnTop", True)))
            if self.pet.isVisible():
                self.pet.show()

        if self.renderer is not None:
            from PySide6.QtCore import QSize

            dpr = self.pet.devicePixelRatioF() or 1.0
            self.renderer.configure(QSize(width, height), dpr,
                                    bool(values.get("pixelated", False)))
            self._configure_clips()
            self.chat.set_avatar(QPixmap.fromImage(self.renderer.atlas.cell_image("idle", 0)))
        self.animator.configure(float(values.get("animationSpeed", 1.0)),
                                bool(values.get("reducedMotion", False)))
        self.pet.set_motion_enabled(not self.animator.paused
                                    and self.animator.state in ("idle", "chin-rest", "review", "waiting", "poke"))

        x, y = values.get("x"), values.get("y")
        if x is None or y is None:
            if initial:
                self._move_to_default_position()
        elif initial:
            self.pet.move(int(x), int(y))

        ai = values.get("ai", {})
        online = ai.get("mode") == "online" and bool(str(ai.get("baseUrl", "")).strip())
        self.chat.set_mode(online, str(ai.get("model", "")))
        self.tray.set_locked(bool(values.get("locked", False)))
        self.tray.set_pet_visible(self.pet.isVisible() if not initial else True)
        self._sync_autostart(bool(values.get("autostart", False)))

        if not initial:
            self._standby()

    def _sync_autostart(self, enabled: bool) -> None:
        try:
            import winreg
        except ImportError:
            return
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        name = "QinChePet"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                winreg.KEY_SET_VALUE) as key:
                if enabled:
                    if getattr(sys, "frozen", False):
                        command = f'"{sys.executable}"'
                    else:
                        command = f'"{sys.executable}" "{Path(__file__).resolve()}"'
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
                else:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
        except OSError:
            pass

    def _on_refresh_pets(self) -> None:
        before = {package.id for package in self.packages}
        self.reload_packages(preferred=str(self.config.get("activePetId")))
        after = {package.id for package in self.packages}
        added = after - before
        self._say(f"找到 {len(self.packages)} 个宠物包" + (f"，新增 {len(added)} 个。" if added else "。"))

    def _open_folder(self, folder: Path) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ------------------------------------------------------------------ #
    def quit(self) -> None:
        if self.pet is not None and self.pet.isVisible():
            self.config.data["x"] = self.pet.x()
            self.config.data["y"] = self.pet.y()
        self.config.save()
        self.bubble.hide()
        self.chat.hide()
        self.settings.hide()
        self.tray.hide()
        self.qapp.quit()


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    shared = QSharedMemory("qinche-desktop-pet-single-instance")
    if not shared.create(1):
        if activate_existing_instance():
            return 0
        QMessageBox.warning(None, APP_NAME,
                            "桌宠已在运行，但未能唤醒对话窗口。\n"
                            "请从托盘退出旧版本后重新启动。")
        return 1

    activation = ActivationServer(app)
    controller = PetApp(app, shared)
    activation.chat_requested.connect(controller.open_chat)
    if controller.package is None:
        QMessageBox.critical(None, APP_NAME,
                             "未找到任何宠物包。\n请把 qinche-q 目录放到：\n"
                             "%USERPROFILE%\\.codex\\pets\\ 或程序目录下的 pets\\")
        return 1
    app.aboutToQuit.connect(lambda: controller.config.save())
    if "--chat" in sys.argv:
        QTimer.singleShot(0, controller.open_chat)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
