"""Regression checks for expressive playback and idle priorities.

Uses offscreen windows, in-memory settings, and no personal pet directories.
Run with .venv/Scripts/python.exe tools/verify_animation.py.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, PropertyMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSharedMemory, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import animation  # noqa: E402
import config  # noqa: E402
import main as pet_main  # noqa: E402
from petpack import DURATIONS, STATE_ROWS  # noqa: E402

BLINK = [[3000, 6000], 60, 60, [70, 100], 60, 60]
CHIN_REST = [180, 180, [2000, 4000], 180, 180, 250]


class QtChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    @staticmethod
    def advance(animator: animation.Animator) -> None:
        # Trigger the same callback as the single-shot timer without waiting
        # several seconds for an intentionally long natural resting pose.
        animator._timer.stop()
        deadline = animator._deadline
        with patch.object(animation, "monotonic", return_value=(
                deadline if deadline is not None else animation.monotonic())):
            animator._tick()


class PlaybackChecks(QtChecks):
    def setUp(self) -> None:
        self.animator = animation.Animator()
        self.frames: list[tuple[str, int]] = []
        self.finished: list[str] = []
        self.animator.frame_changed.connect(lambda state, frame: self.frames.append((state, frame)))
        self.animator.finished.connect(self.finished.append)

    def tearDown(self) -> None:
        self.animator.stop()
        self.animator.deleteLater()
        self.app.processEvents()

    def test_standard_packages_keep_contract_timing(self) -> None:
        for state, durations in DURATIONS.items():
            with self.subTest(state=state):
                self.frames.clear()
                self.finished.clear()
                self.animator.play(state, loop=False)
                for index, duration in enumerate(durations):
                    self.assertEqual(self.frames[-1], (state, index))
                    self.assertEqual(self.animator._timer.interval(), duration)
                    self.advance(self.animator)
                self.assertEqual(len(self.frames), len(durations))
                self.assertEqual(self.finished, [state])
                self.assertFalse(self.animator.playing)

    def test_natural_holds_are_sampled_once_per_frame(self) -> None:
        self.animator.set_clips({"idle": BLINK, "review": CHIN_REST})
        with patch.object(animation.random, "randint", side_effect=[3600, 85, 5800]) as random_duration:
            self.animator.play("idle")
            self.assertEqual(self.animator._timer.interval(), 3600)
            self.animator.configure(speed=2)
            self.assertEqual(self.animator._timer.interval(), 1800)
            self.assertEqual(random_duration.call_count, 1)
            for _ in range(6):
                self.advance(self.animator)
            self.assertEqual(self.animator.frame, 0)
            self.assertEqual(self.animator._timer.interval(), 2900)
            self.assertEqual(random_duration.call_count, 3)

    def test_repeated_loop_requests_do_not_reset_pose(self) -> None:
        self.animator.set_clips({"idle": BLINK})
        self.animator.play("idle")
        self.advance(self.animator)
        before = list(self.frames)
        self.animator.play("idle")
        self.assertEqual(self.animator.frame, 1)
        self.assertEqual(self.frames, before)

    def test_reduced_motion_uses_neutral_frame_and_resumes(self) -> None:
        self.animator.play("review")
        self.advance(self.animator)
        self.animator.configure(paused=True)
        self.assertEqual(self.frames[-1], ("review", 0))
        self.assertTrue(self.animator.playing)
        self.assertFalse(self.animator._timer.isActive())
        self.advance(self.animator)
        self.assertEqual(self.animator.frame, 0)
        self.animator.configure(paused=False)
        self.assertTrue(self.animator._timer.isActive())
        self.advance(self.animator)
        self.assertEqual(self.animator.frame, 1)

    def test_cycles_and_real_timer_complete_once(self) -> None:
        self.animator.set_clips({"short-test": [35, 35]})
        self.animator.play("short-test", loop=False, cycles=2)
        QTest.qWait(220)
        self.assertEqual(self.frames, [("short-test", 0), ("short-test", 1),
                                       ("short-test", 0), ("short-test", 1)])
        self.assertEqual(self.finished, ["short-test"])
        self.assertFalse(self.animator._timer.isActive())

    def test_switching_package_removes_stale_overrides(self) -> None:
        self.animator.set_clips({"idle": BLINK, "extra": [40, 50]})
        self.animator.play("extra")
        self.animator.set_clips({})
        self.assertFalse(self.animator.has_clip("extra"))
        self.assertEqual(self.animator.state, "idle")
        self.assertEqual(self.animator._timer.interval(), DURATIONS["idle"][0])

    def test_invalid_timings_fall_back_without_crashing(self) -> None:
        for values in ([], [0], [float("nan")], [[100, 30]], ["bad"], [True]):
            with self.subTest(values=values):
                self.animator.set_clips({"idle": values})
                self.animator.stop()
                self.animator.play("idle")
                self.assertEqual(self.animator._timer.interval(), DURATIONS["idle"][0])


class ClockChecks(QtChecks):
    """Deterministic event-loop delays, without sleeping or personal settings."""

    def setUp(self) -> None:
        self.now = 100.0
        self.clock = patch.object(animation, "monotonic", side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.animator = animation.Animator()
        self.frames: list[int] = []
        self.animator.frame_changed.connect(lambda _state, frame: self.frames.append(frame))

    def tearDown(self) -> None:
        self.animator.stop()
        self.animator.deleteLater()
        self.app.processEvents()

    def test_precise_timer_and_render_work_do_not_accumulate_drift(self) -> None:
        self.assertEqual(self.animator._timer.timerType(), Qt.TimerType.PreciseTimer)
        self.animator.set_clips({"clock-test": [100, 100, 100]})

        def render_work(_state, _frame):
            self.now += 0.027

        self.animator.frame_changed.connect(render_work)
        self.animator.play("clock-test")
        self.assertEqual(self.animator._timer.interval(), 73)
        for tick in range(1, 51):
            self.now = 100.0 + tick * 0.1 + 1e-9
            self.animator._tick()
            self.assertAlmostEqual(self.animator._deadline, 100.0 + (tick + 1) * 0.1)
            self.assertEqual(self.animator._timer.interval(), 73)
        self.assertEqual(len(self.frames), 51)

    def test_late_callback_skips_expired_short_frame_without_signal_burst(self) -> None:
        self.animator.set_clips({"clock-test": [100, 100, 100]})
        self.animator.play("clock-test")
        self.now += 0.245
        self.animator._tick()
        self.assertEqual(self.frames, [0, 2])
        self.assertEqual(self.animator._timer.interval(), 55)
        self.assertEqual(self.animator.transition_duration_ms(), 55)

    def test_large_delay_has_bounded_catch_up(self) -> None:
        self.animator.set_clips({"clock-test": [60] * 20})
        self.animator.play("clock-test")
        self.now += 60
        self.animator._tick()
        self.assertEqual(self.frames, [0, 4])
        self.assertEqual(self.animator._timer.interval(), 60)
        self.assertAlmostEqual(self.animator._deadline, self.now + 0.06)

    def test_large_delay_preserves_long_rest(self) -> None:
        self.animator.set_clips({"clock-test": [60, 60, 3000, 60]})
        self.animator.play("clock-test")
        self.now += 60
        self.animator._tick()
        self.assertEqual(self.frames, [0, 2])
        self.assertEqual(self.animator.transition_duration_ms(), 3000)
        self.assertEqual(self.animator._timer.interval(), 3000)

    def test_clock_restarts_for_speed_pause_resume_and_package_change(self) -> None:
        self.animator.set_clips({"clock-test": [100, 1000]})
        self.animator.play("clock-test")
        self.now += 0.04
        self.animator.configure(speed=2)
        self.assertEqual(self.animator.transition_duration_ms(), 50)
        self.now = self.animator._deadline
        self.animator._tick()
        self.assertEqual(self.animator.transition_duration_ms(), 500)
        self.animator.configure(speed=2, paused=True)
        self.assertEqual(self.animator.transition_duration_ms(), 0)
        self.assertIsNone(self.animator._deadline)
        self.now += 60
        self.animator.configure(speed=2, paused=False)
        self.assertEqual(self.animator.frame, 0)
        self.assertEqual(self.animator.transition_duration_ms(), 50)
        self.animator.set_clips({"clock-test": [400, 300]})
        self.assertEqual(self.animator.transition_duration_ms(), 200)
        self.animator.stop()
        self.assertEqual(self.animator.transition_duration_ms(), 0)

    def test_early_callback_does_not_advance_frame(self) -> None:
        self.animator.set_clips({"clock-test": [100, 100]})
        self.animator.play("clock-test")
        self.now += 0.08
        self.animator._tick()
        self.assertEqual(self.frames, [0])
        self.assertEqual(self.animator._timer.interval(), 20)


class FakeConfig:
    def __init__(self) -> None:
        self.data = copy.deepcopy(config.DEFAULTS)
        self.data.update(showOnStartup=False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def save(self) -> None:
        pass

    @property
    def ai(self):
        return self.data["ai"]


class ConfigMigrationChecks(unittest.TestCase):
    def test_unversioned_idle_preserves_automatic_behavior_then_saves_explicit_idle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pet-config-test-") as folder:
            root = Path(folder)
            path = root / "settings.json"
            path.write_text(json.dumps({"manualState": "idle", "idleVariety": True}), encoding="utf-8")
            with patch.object(config, "data_dir", return_value=root):
                settings = config.Config()
                self.assertEqual(settings.get("manualState"), "auto")
                self.assertEqual(settings.get("manualStateVersion"), 1)
                settings.save()
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["manualState"], "auto")
                settings.set("manualState", "idle")
                reloaded = config.Config()
                self.assertEqual(reloaded.get("manualState"), "idle")
                self.assertEqual(reloaded.get("manualStateVersion"), 1)

    def test_old_manual_actions_and_disabled_variety_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pet-config-test-") as folder:
            root = Path(folder)
            path = root / "settings.json"
            for state in ("auto", "waving", "running-left"):
                with self.subTest(state=state):
                    path.write_text(json.dumps({"manualState": state, "idleVariety": False}), encoding="utf-8")
                    with patch.object(config, "data_dir", return_value=root):
                        settings = config.Config()
                    self.assertEqual(settings.get("manualState"), state)
                    self.assertFalse(settings.get("idleVariety"))
                    self.assertEqual(settings.get("manualStateVersion"), 1)


class IdlePriorityChecks(QtChecks):
    def setUp(self) -> None:
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
        self.controller.pet.show()
        self.controller._expressive_states = {"idle", "review"}
        self.controller.animator.set_clips({"idle": BLINK, "review": CHIN_REST})
        self.controller.animator.play("idle")

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

    def test_natural_rest_plays_once_without_random_speech(self) -> None:
        self.controller._idle_variety()
        self.assertEqual(self.controller.animator.state, "review")
        self.assertTrue(14000 <= self.controller._idle_timer.interval() <= 30000)
        self.controller._say.assert_not_called()
        for _ in range(6):
            self.advance(self.controller.animator)
        self.assertEqual(self.controller.animator.state, "idle")

    def test_blink_finishes_before_rest_pose(self) -> None:
        self.advance(self.controller.animator)
        self.controller._idle_variety()
        self.assertEqual(self.controller.animator.state, "idle")
        self.assertEqual(self.controller._idle_timer.interval(), 250)
        for _ in range(5):
            self.advance(self.controller.animator)
        self.controller._idle_variety()
        self.assertEqual(self.controller.animator.state, "review")

    def test_idle_does_not_override_user_settings_or_hidden_pet(self) -> None:
        for key, value in (("idleVariety", False), ("reducedMotion", True),
                           ("manualState", "running"), ("manualState", "idle")):
            with self.subTest(setting=key):
                original = self.controller.config.data[key]
                self.controller.config.data[key] = value
                self.controller._idle_variety()
                self.assertEqual(self.controller.animator.state, "idle")
                self.controller.config.data[key] = original
        self.controller.pet.hide()
        self.controller._idle_variety()
        self.assertEqual(self.controller.animator.state, "idle")

    def test_explicit_idle_setting_is_shown_and_keeps_only_idle_animation(self) -> None:
        values = copy.deepcopy(self.controller.config.data)
        values["manualState"] = "idle"
        self.controller._on_settings_applied(values)
        self.assertEqual(self.controller.settings.state_box.currentData(), "idle")
        self.controller._idle_variety()
        self.assertEqual(self.controller.animator.state, "idle")
        self.advance(self.controller.animator)
        self.assertEqual(self.controller.animator.frame, 1)
        self.assertTrue(self.controller.animator.playing)

    def test_idle_preview_finishes_before_automatic_variety_can_run(self) -> None:
        self.controller._on_state_preview("idle")
        self.assertTrue(self.controller._state_preview_active)
        self.controller._idle_variety()
        self.assertEqual(self.controller.animator.state, "idle")
        for _ in range(len(BLINK) * 2):
            self.advance(self.controller.animator)
        self.assertFalse(self.controller._state_preview_active)
        self.controller._idle_variety()
        self.assertEqual(self.controller.animator.state, "review")

    def test_drag_or_poke_can_end_preview_without_leaving_automatic_variety_blocked(self) -> None:
        self.controller._on_state_preview("idle")
        self.controller._on_drag_move("left")
        self.assertFalse(self.controller._state_preview_active)
        self.controller._on_drag_end()
        self.controller._on_state_preview("idle")
        self.controller._on_click()
        self.assertFalse(self.controller._state_preview_active)
        self.controller._standby()
        self.controller._idle_variety()
        self.assertEqual(self.controller.animator.state, "review")

    def test_drag_and_pending_reply_take_priority(self) -> None:
        self.controller._on_drag_move("left")
        self.controller._reply_pending = True
        self.controller._idle_variety()
        self.controller._standby()
        self.assertEqual(self.controller.animator.state, "running-left")
        self.controller._on_drag_end()
        self.assertEqual(self.controller.animator.state, "waiting")
        self.controller._idle_variety()
        self.assertEqual(self.controller.animator.state, "waiting")
        self.controller._reply_pending = False
        self.controller.config.data["manualState"] = "running"
        self.controller._standby()
        self.assertEqual(self.controller.animator.state, "running")

    def test_online_worker_busy_blocks_idle_action(self) -> None:
        with patch.object(type(self.controller.llm), "busy", new_callable=PropertyMock, return_value=True):
            self.controller._idle_variety()
        self.assertEqual(self.controller.animator.state, "idle")

    def test_reduced_motion_remains_paused_after_settings(self) -> None:
        self.controller.config.data["reducedMotion"] = True
        self.controller._apply_settings(self.controller.config.data)
        self.assertTrue(self.controller.animator.paused)
        self.assertEqual(self.controller.animator.frame, 0)
        self.assertFalse(self.controller.animator._timer.isActive())
        self.controller._idle_variety()
        self.assertEqual(self.controller.animator.state, "idle")

    def test_legacy_idle_still_works_without_forced_jumping(self) -> None:
        self.controller._expressive_states.clear()
        self.controller.animator.set_clips({})
        self.controller._idle_variety()
        self.assertIn(self.controller.animator.state, ("waving", "review"))
        self.assertTrue(18000 <= self.controller._idle_timer.interval() <= 42000)
        self.controller._say.assert_not_called()

    def test_automatic_variety_uses_available_quiet_actions_without_repeating(self) -> None:
        quiet = ("chin-rest", "review", "waiting", "waving")
        clips = {state: [120, 120, 120] for state in (*quiet, "failed", "jumping", "running")}
        clips["idle"] = BLINK
        self.controller._expressive_states = set(clips)
        self.controller.animator.set_clips(clips)
        seen = []
        with patch.object(pet_main.random, "choice", side_effect=lambda options: options[0]):
            for _ in range(8):
                self.controller._idle_variety()
                state = self.controller.animator.state
                self.assertIn(state, quiet)
                if seen:
                    self.assertNotEqual(state, seen[-1])
                seen.append(state)
                for _ in clips[state]:
                    self.advance(self.controller.animator)
                self.assertEqual(self.controller.animator.state, "idle")
        self.controller._say.assert_not_called()

    def test_stream_changes_from_waiting_to_working_once_without_resetting_frames(self) -> None:
        self.controller.chat.begin_stream()
        self.controller._reply_pending = True
        self.controller._standby()
        self.assertEqual(self.controller.animator.state, "waiting")
        self.controller.llm.delta.emit("")
        self.assertEqual(self.controller.animator.state, "waiting")
        self.controller.llm.delta.emit("你好")
        self.assertTrue(self.controller._reply_streaming)
        self.assertEqual(self.controller.animator.state, "running")
        self.advance(self.controller.animator)
        frame = self.controller.animator.frame
        deadline = self.controller.animator._deadline
        for _ in range(30):
            self.controller.llm.delta.emit("。")
        self.assertEqual(self.controller.animator.frame, frame)
        self.assertEqual(self.controller.animator._deadline, deadline)
        self.controller.llm.done.emit("")
        self.assertFalse(self.controller._reply_pending)
        self.assertFalse(self.controller._reply_streaming)
        self.assertEqual(self.controller.animator.state, "idle")
        self.assertEqual(self.controller._history[-1]["content"], "你好" + "。" * 30)

    def test_stream_remembers_working_state_while_drag_takes_priority(self) -> None:
        self.controller.chat.begin_stream()
        self.controller._reply_pending = True
        self.controller._on_drag_move("right")
        self.controller.llm.delta.emit("在回复")
        self.assertEqual(self.controller.animator.state, "running-right")
        self.controller._on_drag_end()
        self.assertEqual(self.controller.animator.state, "running")
        self.controller._on_click()
        self.assertEqual(self.controller.animator.state, "running")
        self.assertFalse(self.controller._poke_queued)

    def test_failed_reply_clears_streaming_and_recovers_to_manual_action(self) -> None:
        self.controller.config.data["manualState"] = "waving"
        self.controller._reply_pending = True
        self.controller._reply_streaming = True
        self.controller._on_llm_error("测试错误")
        self.assertFalse(self.controller._reply_streaming)
        self.assertFalse(self.controller._reply_pending)
        self.assertEqual(self.controller.animator.state, "failed")
        for _ in range(len(DURATIONS["failed"]) * 2):
            self.advance(self.controller.animator)
        self.assertEqual(self.controller.animator.state, "waving")

    def test_all_manual_previews_finish_and_restore_idle(self) -> None:
        for state in STATE_ROWS:
            with self.subTest(state=state):
                self.controller._on_state_preview(state)
                self.assertEqual(self.controller.animator.state, state)
                count = len(self.controller.animator._durations[state])
                for _ in range(count * 2):
                    self.advance(self.controller.animator)
                self.assertEqual(self.controller.animator.state, "idle")

    def test_preview_cannot_interrupt_drag_or_pending_reply(self) -> None:
        self.controller._reply_pending = True
        self.controller._on_state_preview("jumping")
        self.assertEqual(self.controller.animator.state, "waiting")
        self.controller._reply_streaming = True
        self.controller._on_state_preview("waving")
        self.assertEqual(self.controller.animator.state, "running")
        self.controller._on_drag_move("left")
        self.controller._on_state_preview("failed")
        self.assertEqual(self.controller.animator.state, "running-left")

    def test_streaming_stays_static_with_reduced_motion(self) -> None:
        self.controller.config.data["reducedMotion"] = True
        self.controller._apply_settings(self.controller.config.data)
        self.controller.chat.begin_stream()
        self.controller._reply_pending = True
        self.controller._standby()
        self.controller.llm.delta.emit("静态回复")
        self.assertEqual(self.controller.animator.state, "running")
        self.assertEqual(self.controller.animator.frame, 0)
        self.assertFalse(self.controller.animator._timer.isActive())

    def test_all_available_actions_are_preloaded_and_blink_frames_are_state_specific(self) -> None:
        clips = {state: [100] * 6 for state in (*STATE_ROWS, "poke", "chin-rest")}
        self.controller.animator.stop()
        self.controller.package = SimpleNamespace(manifest={"animationClips": {
            "idle": {"blinkFrames": [2, False, -1, 99, "3"]},
            "chin-rest": {"blinkFrames": [3]},
            "running": {"blinkFrames": "bad"},
        }})
        prepare = Mock()
        self.controller.renderer = SimpleNamespace(
            atlas=SimpleNamespace(clip_durations=lambda: clips), prepare_frames=prepare)
        self.controller._configure_clips()
        prepare.assert_called_once()
        self.assertEqual(set(prepare.call_args.args[0]), set(clips))
        self.assertEqual(prepare.call_args.args[0][:2], ["idle", "poke"])
        self.assertEqual(self.controller._blink_frames["idle"], frozenset({2}))
        self.assertEqual(self.controller._blink_frames["poke"], frozenset({2}))
        self.assertEqual(self.controller._blink_frames["chin-rest"], frozenset({3}))
        self.assertEqual(self.controller._blink_frames["review"], frozenset())
        self.assertNotIn("running", self.controller._blink_frames)


if __name__ == "__main__":
    unittest.main(verbosity=2)
