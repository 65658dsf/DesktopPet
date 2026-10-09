"""Check lively poke playback without loading personal settings or networking.

Run with .venv/Scripts/python.exe tools/verify_poke.py.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import PropertyMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSharedMemory, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import animation  # noqa: E402
import config  # noqa: E402
import main as pet_main  # noqa: E402
from petpack import _load_package  # noqa: E402

POKE = [80, 65, 75, 125, 300, 120, 110, 210]


class FakeConfig:
    def __init__(self) -> None:
        self.data = copy.deepcopy(config.DEFAULTS)
        self.data.update(showOnStartup=False, idleVariety=False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def save(self) -> None:
        pass

    @property
    def ai(self):
        return self.data["ai"]


class PokeChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.now = 100.0
        for replacement in (
            patch.object(pet_main, "Config", FakeConfig),
            patch.object(pet_main, "scan_packages", return_value=[]),
            patch.object(pet_main.PetApp, "_sync_autostart"),
            patch.object(pet_main.PetApp, "_say"),
            patch.object(pet_main.Tray, "show"),
            patch.object(pet_main, "bubble_line", side_effect=lambda kind: kind),
            patch.object(pet_main, "monotonic", side_effect=lambda: self.now),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)
        self.controller = pet_main.PetApp(self.app, QSharedMemory())
        self.controller.pet.show()
        self.controller._expressive_states = {"poke"}
        self.animator = self.controller.animator
        self.animator.set_clips({"poke": POKE})
        self.animator.play("idle")
        self.frames: list[tuple[str, int]] = []
        self.animator.frame_changed.connect(lambda state, frame: self.frames.append((state, frame)))

    def tearDown(self) -> None:
        for timer in self.controller.findChildren(pet_main.QTimer):
            timer.stop()
        self.controller.tray.hide()
        for window in (self.controller.pet, self.controller.bubble,
                       self.controller.chat, self.controller.settings):
            window.hide()
            window.deleteLater()
        self.controller.deleteLater()
        self.app.processEvents()

    def advance(self, count: int = 1) -> None:
        for _ in range(count):
            self.animator._timer.stop()
            deadline = self.animator._deadline
            with patch.object(animation, "monotonic", return_value=(
                    deadline if deadline is not None else animation.monotonic())):
                self.animator._tick()

    def test_single_poke_finishes_every_pose_then_returns_to_idle(self) -> None:
        self.controller._on_click()
        self.advance(len(POKE))
        self.assertEqual(self.frames, [("poke", index) for index in range(len(POKE))] + [("idle", 0)])
        self.assertEqual(self.animator.state, "idle")
        self.assertFalse(self.controller._poke_queued)
        self.controller._say.assert_called_once_with("poke_soft")

    def test_real_click_plays_shipped_artwork_then_returns_to_idle(self) -> None:
        package = _load_package(ROOT / "pets/qinche-q")
        self.assertIsNotNone(package)
        self.controller._install_package(package)
        self.animator.play("idle")
        self.frames.clear()
        atlas = self.controller.renderer.atlas
        self.assertEqual(atlas.clip_errors, {})
        self.assertEqual(atlas.frames("poke"), len(POKE))
        QTest.mouseClick(self.controller.pet, Qt.MouseButton.LeftButton)
        self.assertEqual(self.animator.state, "poke")
        self.assertFalse(self.controller.pet._pixmap.isNull())
        self.advance(atlas.frames("poke"))
        self.assertEqual(self.frames, [("poke", index) for index in range(len(POKE))] + [("idle", 0)])
        self.assertEqual(self.animator.state, "idle")

    def test_rapid_pokes_preserve_frame_and_queue_only_one_complete_replay(self) -> None:
        self.controller._on_click()
        self.advance(4)
        previous_frames = list(self.frames)
        deadline = self.animator._deadline
        for _ in range(25):
            self.controller._on_click()
        self.assertEqual(self.frames, previous_frames)
        self.assertEqual(self.animator.frame, 4)
        self.assertEqual(self.animator._deadline, deadline)
        self.advance(len(POKE) - 4)
        self.assertEqual(self.animator.state, "poke")
        self.assertEqual(self.animator.frame, 0)
        self.assertFalse(self.controller._poke_queued)
        self.advance(len(POKE))
        self.assertEqual(self.animator.state, "idle")
        poke_frames = [frame for state, frame in self.frames if state == "poke"]
        self.assertEqual(poke_frames, list(range(len(POKE))) * 2)
        self.assertEqual(self.controller._say.call_count, 26)

    def test_burst_speech_resets_after_a_break(self) -> None:
        self.controller._on_click()
        self.now += 0.3
        self.controller._on_click()
        self.now += 0.3
        self.controller._on_click()
        self.now += pet_main.POKE_BURST_SECONDS + 0.01
        self.controller._on_click()
        self.assertEqual([call.args[0] for call in self.controller._say.call_args_list],
                         ["poke_soft", "poke", "poke_repeat", "poke_soft"])

    def test_new_package_never_falls_back_to_old_fifth_click_jump(self) -> None:
        for _ in range(10):
            self.now += 3.0
            self.controller._on_click()
            self.assertEqual(self.animator.state, "poke")
            self.advance(len(POKE))
        self.assertTrue(all(state in ("poke", "idle") for state, _frame in self.frames))

    def test_legacy_package_keeps_wave_and_jump(self) -> None:
        self.controller._expressive_states.clear()
        self.animator.set_clips({})
        for count in range(1, 6):
            self.controller._on_click()
            self.assertEqual(self.animator.state, "jumping" if count == 5 else "waving")

    def test_drag_cancels_queued_reaction_and_keeps_priority(self) -> None:
        self.controller._on_click()
        self.controller._on_click()
        self.assertTrue(self.controller._poke_queued)
        self.controller._on_drag_move("left")
        self.controller._on_click()
        self.assertEqual(self.animator.state, "running-left")
        self.assertFalse(self.controller._poke_queued)
        self.controller._on_drag_end()
        self.assertEqual(self.animator.state, "idle")

    def test_pending_reply_or_busy_worker_does_not_get_interrupted(self) -> None:
        self.controller._reply_pending = True
        self.controller._standby()
        self.controller._on_click()
        self.assertEqual(self.animator.state, "waiting")
        self.assertFalse(self.controller._poke_queued)
        self.controller._reply_pending = False
        self.controller._standby()
        with patch.object(type(self.controller.llm), "busy", new_callable=PropertyMock, return_value=True):
            self.controller._on_click()
        self.assertEqual(self.animator.state, "idle")

    def test_reduced_motion_keeps_pose_and_speaks(self) -> None:
        self.controller.config.data["reducedMotion"] = True
        self.animator.configure(paused=True)
        for _ in range(6):
            self.controller._on_click()
        self.assertEqual(self.frames, [])
        self.assertEqual(self.animator.state, "idle")
        self.assertFalse(self.animator._timer.isActive())
        self.assertFalse(self.controller._poke_queued)
        self.assertEqual(self.controller._say.call_count, 6)

    def test_opening_chat_cancels_reaction_and_queued_replay(self) -> None:
        self.controller._on_click()
        self.controller._on_click()
        self.controller.open_chat()
        self.assertTrue(self.controller.chat.isVisible())
        self.assertEqual(self.animator.state, "idle")
        self.assertFalse(self.controller._poke_queued)

    def test_sending_chat_cancels_queue_before_waiting(self) -> None:
        self.controller._on_click()
        self.controller._on_click()
        self.controller.config.ai.update(mode="online", baseUrl="http://test.invalid")
        with patch.object(self.controller.llm, "send") as send:
            self.controller._on_send("你好")
            send.assert_called_once()
        self.assertEqual(self.animator.state, "waiting")
        self.assertTrue(self.controller._reply_pending)
        self.assertFalse(self.controller._poke_queued)

    def test_preview_and_package_change_clear_queued_replay(self) -> None:
        self.controller._on_click()
        self.controller._on_click()
        self.controller._on_state_preview("review")
        self.assertEqual(self.animator.state, "review")
        self.assertFalse(self.controller._poke_queued)
        self.controller._on_click()
        self.controller._on_click()
        self.controller._configure_clips()
        self.assertEqual(self.animator.state, "idle")
        self.assertFalse(self.animator.has_clip("poke"))
        self.assertFalse(self.controller._poke_queued)

    def test_hidden_pet_does_not_start_replay(self) -> None:
        self.controller._on_click()
        self.controller._on_click()
        self.controller.pet.hide()
        self.advance(len(POKE))
        self.assertEqual(self.animator.state, "idle")
        self.assertFalse(self.controller._poke_queued)


if __name__ == "__main__":
    unittest.main(verbosity=2)
