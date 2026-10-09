"""Check frame interpolation and render caching without personal pet settings."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPixmap  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pet_window import PetWindow, SpriteRenderer  # noqa: E402
from petpack import _load_package  # noqa: E402


class FrameTransitionChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.pet = PetWindow()
        self.pet.set_motion_enabled(False)
        self.pet.resize(48, 48)
        self.pet.show()
        self.app.processEvents()
        self.red = self.frame(QColor(255, 0, 0))
        self.blue = self.frame(QColor(0, 0, 255))
        self.green = self.frame(QColor(0, 255, 0))
        self.pet.set_frame(self.red)

    def tearDown(self) -> None:
        self.pet.close()
        self.pet.deleteLater()
        self.app.processEvents()

    @staticmethod
    def frame(color: QColor, size: int = 48, dpr: float = 1.0) -> QPixmap:
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(color)
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(dpr)
        return pixmap

    @staticmethod
    def pixel(pixmap: QPixmap) -> QColor:
        return pixmap.toImage().pixelColor(0, 0)

    def test_opaque_blend_does_not_fade_pet_or_darken_colors(self) -> None:
        for progress in (0.1, 0.25, 0.5, 0.75, 0.9):
            with self.subTest(progress=progress):
                color = self.pixel(PetWindow._blend_frames(self.red, self.blue, progress))
                self.assertAlmostEqual(color.alpha(), 255, delta=2)
                self.assertAlmostEqual(color.red(), 255 * (1 - progress), delta=2)
                self.assertAlmostEqual(color.blue(), 255 * progress, delta=2)

    def test_premultiplied_alpha_is_interpolated_instead_of_source_over(self) -> None:
        previous = self.frame(QColor(255, 0, 0, 128))
        target = self.frame(QColor(0, 0, 255, 64))
        midpoint = self.pixel(PetWindow._blend_frames(previous, target, 0.5))
        self.assertAlmostEqual(midpoint.alpha(), 96, delta=2)
        self.assertAlmostEqual(midpoint.red(), 170, delta=3)
        self.assertAlmostEqual(midpoint.blue(), 85, delta=3)
        transparent = self.frame(QColor(0, 0, 0, 0))
        self.assertEqual(self.pixel(PetWindow._blend_frames(transparent, transparent, 0.5)).alpha(), 0)

    def test_real_timer_produces_intermediate_pose_and_completes(self) -> None:
        self.pet.set_frame(self.blue, transition_ms=180)
        self.assertEqual(self.pet._pixmap.cacheKey(), self.red.cacheKey())
        self.assertTrue(self.pet._motion_timer.isActive())
        self.assertEqual(self.pet._motion_timer.timerType(), Qt.TimerType.PreciseTimer)
        QTest.qWait(70)
        color = self.pixel(self.pet._pixmap)
        self.assertGreater(color.blue(), 0)
        self.assertGreater(color.red(), 0)
        QTest.qWait(150)
        self.assertEqual(self.pet._pixmap.cacheKey(), self.blue.cacheKey())
        self.assertFalse(self.pet._transition_clock.isValid())
        self.assertFalse(self.pet._motion_timer.isActive())

    def test_delayed_render_uses_elapsed_time_without_replaying_missed_ticks(self) -> None:
        self.pet.set_frame(self.blue, transition_ms=60)
        QTest.qSleep(100)  # Block delivery just like a busy GUI event loop.
        self.pet._render_tick()
        self.assertEqual(self.pet._pixmap.cacheKey(), self.blue.cacheKey())
        self.assertFalse(self.pet._motion_timer.isActive())

    def test_interruption_continues_from_current_blend_without_jump(self) -> None:
        self.pet.set_frame(self.blue, transition_ms=240)
        QTest.qWait(70)
        self.pet._advance_transition()
        before = self.pixel(self.pet._pixmap)
        self.pet.set_frame(self.green, transition_ms=120)
        after = self.pixel(self.pet._pixmap)
        self.assertAlmostEqual(before.red(), after.red(), delta=4)
        self.assertAlmostEqual(before.blue(), after.blue(), delta=4)
        self.assertEqual(after.green(), 0)
        QTest.qWait(160)
        self.assertEqual(self.pet._pixmap.cacheKey(), self.green.cacheKey())

    def test_repeated_target_does_not_restart_transition(self) -> None:
        self.pet.set_frame(self.blue, transition_ms=150)
        QTest.qWait(60)
        elapsed = self.pet._transition_clock.elapsed()
        self.pet.set_frame(self.blue, transition_ms=150)
        self.assertGreaterEqual(self.pet._transition_clock.elapsed(), elapsed)
        QTest.qWait(130)
        self.assertEqual(self.pet._pixmap.cacheKey(), self.blue.cacheKey())

    def test_hidden_and_dragged_pet_finish_blend_and_release_timer(self) -> None:
        self.pet.set_frame(self.blue, transition_ms=200)
        self.pet.hide()
        self.assertEqual(self.pet._pixmap.cacheKey(), self.blue.cacheKey())
        self.assertFalse(self.pet._transition_clock.isValid())
        self.assertFalse(self.pet._motion_timer.isActive())
        self.pet.set_frame(self.green, transition_ms=200)
        self.assertEqual(self.pet._pixmap.cacheKey(), self.green.cacheKey())
        self.pet.show()
        self.pet.set_frame(self.red, transition_ms=200)
        self.pet._dragging = True
        self.pet._sync_motion()
        self.assertEqual(self.pet._pixmap.cacheKey(), self.red.cacheKey())
        self.assertFalse(self.pet._motion_timer.isActive())
        self.pet.set_frame(self.blue, transition_ms=200)
        self.assertEqual(self.pet._pixmap.cacheKey(), self.blue.cacheKey())

    def test_reduced_motion_disables_blends_independently_of_breath(self) -> None:
        self.pet.set_frame(self.blue, transition_ms=200)
        self.assertTrue(self.pet._transition_clock.isValid())
        self.pet.set_transitions_enabled(False)
        self.assertEqual(self.pet._pixmap.cacheKey(), self.blue.cacheKey())
        self.assertFalse(self.pet._motion_timer.isActive())
        self.pet.set_frame(self.green, transition_ms=200)
        self.assertEqual(self.pet._pixmap.cacheKey(), self.green.cacheKey())
        self.pet.set_transitions_enabled(True)
        self.pet.set_frame(self.red, transition_ms=200)
        self.assertTrue(self.pet._transition_clock.isValid())

    def test_size_or_dpr_change_snaps_to_new_configuration(self) -> None:
        for target in (self.frame(QColor(0, 0, 255), size=64),
                       self.frame(QColor(0, 0, 255), dpr=2.0)):
            with self.subTest(size=target.size(), dpr=target.devicePixelRatio()):
                self.pet.set_frame(self.red)
                self.pet.set_frame(target, transition_ms=100)
                self.assertEqual(self.pet._pixmap.cacheKey(), target.cacheKey())
                self.assertFalse(self.pet._transition_clock.isValid())
        same_dpr = self.frame(QColor(255, 0, 0), dpr=2.0)
        blended = PetWindow._blend_frames(same_dpr, target, 0.5)
        self.assertEqual(blended.devicePixelRatio(), 2.0)
        self.assertEqual(blended.size(), target.size())
        self.assertAlmostEqual(blended.toImage().pixelColor(47, 47).alpha(), 255, delta=2)

    def test_prewarmed_frames_are_reused_until_configuration_changes(self) -> None:
        package = _load_package(ROOT / "pets" / "qinche-q")
        self.assertIsNotNone(package)
        renderer = SpriteRenderer(package)
        renderer.configure(QSize(192, 208), 1.5, False)
        states = ("idle", "review", "running-left")
        renderer.prepare_frames(states)
        expected = sum(renderer.atlas.frames(state) for state in states)
        self.assertEqual(len(renderer._cache), expected)
        old_frame = renderer.pixmap("idle", 0)
        with patch.object(renderer.atlas, "cell_image", side_effect=AssertionError("decoded during playback")):
            renderer.prepare_frames(states)
            for state in states:
                for index in range(renderer.atlas.frames(state)):
                    self.assertFalse(renderer.pixmap(state, index).isNull())
        renderer.configure(QSize(288, 312), 2.0, False)
        self.assertEqual(renderer._cache, {})
        renderer.prepare_frames(states)
        resized = renderer.pixmap("idle", 0)
        self.assertIsNot(resized, old_frame)
        self.assertEqual(resized.size(), QSize(576, 624))
        self.assertEqual(resized.devicePixelRatio(), 2.0)

    def test_prewarming_obeys_budget_and_keeps_lazy_playback_available(self) -> None:
        package = _load_package(ROOT / "pets" / "qinche-q")
        renderer = SpriteRenderer(package)
        renderer.configure(QSize(192, 208), 1.0, False)
        one_frame_bytes = 192 * 208 * 4
        renderer.prepare_frames(("idle", "review"), max_bytes=one_frame_bytes * 2)
        self.assertEqual(len(renderer._cache), 2)
        self.assertEqual(set(renderer._cache), {("idle", 0), ("review", 0)})
        self.assertFalse(renderer.pixmap("review", 5).isNull())
        renderer.configure(QSize(288, 312), 2.0, False)
        renderer.prepare_frames(("idle", "review"), max_bytes=one_frame_bytes)
        self.assertEqual(renderer._cache, {})

    def test_lazy_playback_evicts_least_recently_used_frames_under_hard_budget(self) -> None:
        image = self.red.toImage()
        renderer = SpriteRenderer(SimpleNamespace())
        renderer.size = QSize(48, 48)
        renderer.atlas = SimpleNamespace(frames=lambda state: 8,
                                         cell_image=lambda state, index: QImage(image))
        one_frame_bytes = 48 * 48 * 4
        renderer.CACHE_LIMIT_BYTES = one_frame_bytes * 3
        for index in range(3):
            renderer.pixmap("first", index)
        hot_frame = renderer.pixmap("first", 0)
        renderer.pixmap("second", 0)
        self.assertNotIn(("first", 1), renderer._cache)
        self.assertIs(renderer.pixmap("first", 0), hot_frame)
        for state in ("first", "second", "third"):
            for index in range(8):
                self.assertFalse(renderer.pixmap(state, index).isNull())
                actual = sum(frame.width() * frame.height() * 4 for frame in renderer._cache.values())
                self.assertEqual(renderer._cache_bytes, actual)
                self.assertLessEqual(actual, renderer.CACHE_LIMIT_BYTES)
        self.assertEqual(len(renderer._cache), 3)

    def test_warming_starts_every_action_and_does_not_evict_recent_playback(self) -> None:
        image = self.red.toImage()
        renderer = SpriteRenderer(SimpleNamespace())
        renderer.size = QSize(48, 48)
        renderer.atlas = SimpleNamespace(frames=lambda state: 6,
                                         cell_image=lambda state, index: QImage(image))
        renderer.CACHE_LIMIT_BYTES = 48 * 48 * 4 * 4
        renderer.prepare_frames(("idle", "waiting", "running", "failed"), max_bytes=2**30)
        self.assertEqual(set(renderer._cache), {
            ("idle", 0), ("waiting", 0), ("running", 0), ("failed", 0)})
        renderer.pixmap("poke", 2)
        before = list(renderer._cache.items())
        renderer.prepare_frames(("idle", "waiting", "running", "failed"))
        self.assertEqual(list(renderer._cache.items()), before)

    def test_frame_larger_than_cache_budget_can_render_without_retention(self) -> None:
        image = self.red.toImage()
        renderer = SpriteRenderer(SimpleNamespace())
        renderer.size = QSize(48, 48)
        renderer.atlas = SimpleNamespace(cell_image=lambda state, index: QImage(image))
        renderer.CACHE_LIMIT_BYTES = 48 * 48 * 4 - 1
        frame = renderer.pixmap("idle", 0)
        self.assertFalse(frame.isNull())
        self.assertEqual(renderer._cache_bytes, 0)
        self.assertEqual(renderer._cache, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
