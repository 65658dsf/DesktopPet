"""Exercise optional animation clips without touching installed pets or settings."""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from petpack import Atlas, PetPackage, STATE_FRAMES
from pet_window import PetWindow, SpriteRenderer

APP = QApplication.instance() or QApplication([])


class ExpressionAssets(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="desktop-pet-clips-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.core = QImage(1536, 1872, QImage.Format.Format_RGBA8888)
        self.core.fill(QColor(25, 50, 75, 255))
        self.assertTrue(self.core.save(str(self.root / "core.png")))
        self.bounds = [(20, 10, 50, 70), (40, 18, 45, 80), (18, 10, 70, 90),
                       (10, 15, 55, 75), (30, 20, 65, 80), (15, 8, 60, 85)]
        self.sheet = QImage(360, 240, QImage.Format.Format_RGBA8888)
        self.sheet.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self.sheet)
        for i, (x, y, width, height) in enumerate(self.bounds):
            origin_x, origin_y = i % 3 * 120, i // 3 * 120
            painter.fillRect(origin_x + x, origin_y + y, width, height, QColor(40 + i * 20, 60, 90))
            painter.fillRect(origin_x, origin_y, 1, 1, QColor(255, 255, 255, 10))
        painter.end()
        self.assertTrue(self.sheet.save(str(self.root / "clip.png")))
        self.spec = {"spritesheetPath": "clip.png", "columns": 3, "frameCount": 6,
                     "durations": [[2500, 4200], 85, 95, 90, 120, 180],
                     "contentHeight": 80, "baseline": 190}
        self.manifest = {"id": "test", "spritesheetPath": "core.png",
                         "animationClips": {"idle": copy.deepcopy(self.spec)}}

    def atlas(self, manifest=None) -> Atlas:
        return Atlas(PetPackage(self.root, manifest or self.manifest), 1)

    def test_native_frames_share_size_scale_baseline_and_preserve_alpha(self) -> None:
        atlas = self.atlas()
        self.assertEqual(atlas.clip_errors, {})
        self.assertEqual(atlas.frames("idle"), 6)
        self.assertEqual(atlas.clip_durations()["idle"][0], (2500, 4200))
        frames = [atlas.cell_image("idle", index) for index in range(6)]
        for i, frame in enumerate(frames):
            self.assertEqual(frame.size(), frames[0].size())
            self.assertEqual(frame.width() * 208, frame.height() * 192)
            x, y, width, height = Atlas._alpha_bounds(frame)
            # Content remains in its native pixels: no per-frame stretching.
            self.assertEqual((width, height), self.bounds[i][2:])
            density = frame.width() / 192
            self.assertEqual(y + height, round(190 * density))
            self.assertLessEqual(abs(x * 2 + width - frame.width()), 1)
            self.assertLessEqual(height / density, 80)
            self.assertEqual(frame.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(atlas.cell_image("idle", -10), frames[0])
        self.assertEqual(atlas.cell_image("idle", 900), frames[-1])

    def test_explicit_rectangles_and_custom_state(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec.update(frameCount=2, durations=[500, 90], frames=[
            {"rect": [240, 120, 120, 120]}, {"rect": [0, 0, 120, 120]}])
        self.manifest["animationClips"]["thinking"] = spec
        atlas = self.atlas()
        self.assertEqual(atlas.frames("thinking"), 2)
        first = atlas.cell_image("thinking", 0)
        x, y, _, _ = Atlas._alpha_bounds(first)
        self.assertEqual(first.pixelColor(x, y).red(), 140)
        self.assertEqual(atlas.clip_durations()["thinking"], [500, 90])

    def test_width_limit_keeps_wide_pose_inside_logical_cell(self) -> None:
        self.manifest["animationClips"]["idle"]["contentHeight"] = 190
        atlas = self.atlas()
        frame = atlas.cell_image("idle", 2)
        x, y, width, height = Atlas._alpha_bounds(frame)
        self.assertLessEqual(width / (frame.width() / 192), 180)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(y + height, frame.height())

    def test_logical_offsets_keep_native_pixels_and_restore_jump_trajectory(self) -> None:
        still = self.atlas()
        offsets = [[0, 0], [-2.5, 4], [3.5, -24], [1, -40], [0, -12], [0, 0]]
        self.manifest["animationClips"]["idle"]["offsets"] = offsets
        moving = self.atlas()
        self.assertEqual(moving.clip_errors, {})
        for index, (offset_x, offset_y) in enumerate(offsets):
            original = still.cell_image("idle", index)
            frame = moving.cell_image("idle", index)
            self.assertEqual(frame.size(), original.size())
            old_x, old_y, old_width, old_height = Atlas._alpha_bounds(original)
            x, y, width, height = Atlas._alpha_bounds(frame)
            density = frame.width() / 192
            self.assertEqual((width, height), (old_width, old_height))
            self.assertEqual(x, old_x + round(offset_x * density))
            self.assertEqual(y + height, round((190 + offset_y) * density))
            # Cropping to the visible content yields exactly the same source
            # pixels; moving a pose must not rescale or otherwise redraw it.
            self.assertEqual(frame.copy(x, y, width, height),
                             original.copy(old_x, old_y, width, height))

    def test_offsets_follow_explicit_frame_order(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec.update(frameCount=2, durations=[100, 100], offsets=[[5, -20], [-5, 0]],
                    frames=[{"rect": [240, 120, 120, 120]}, {"rect": [0, 0, 120, 120]}])
        self.manifest["animationClips"]["jumping"] = spec
        atlas = self.atlas()
        self.assertEqual(atlas.clip_errors, {})
        for index, (expected_red, offset_y) in enumerate([(140, -20), (40, 0)]):
            frame = atlas.cell_image("jumping", index)
            x, y, _, height = Atlas._alpha_bounds(frame)
            self.assertEqual(frame.pixelColor(x, y).red(), expected_red)
            self.assertEqual(y + height, round((190 + offset_y) * frame.width() / 192))

    def test_malformed_or_clipping_offsets_fall_back(self) -> None:
        invalid_offsets = [
            None, [], [[0, 0]], [0] * 6, [[0]] * 6, [[0, 0, 0]] * 6,
            [[True, 0]] * 6, [["0", 0]] * 6, [[float("nan"), 0]] * 6,
            [[0, float("inf")]] * 6, [[193, 0]] * 6, [[0, -209]] * 6,
            [[95, 0]] * 6, [[0, -190]] * 6, [[0, 19]] * 6,
        ]
        for offsets in invalid_offsets:
            with self.subTest(offsets=offsets), self.assertLogs("petpack", logging.WARNING):
                manifest = copy.deepcopy(self.manifest)
                manifest["animationClips"]["review"] = {**self.spec, "offsets": offsets}
                atlas = self.atlas(manifest)
            self.assertIn("review", atlas.clip_errors)
            self.assertEqual(set(atlas.clip_durations()), {"idle"})
            self.assertEqual(atlas.frames("review"), STATE_FRAMES["review"])

    def test_bad_clip_falls_back_without_disabling_other_states(self) -> None:
        invalid_specs = [
            {**self.spec, "spritesheetPath": "../outside.png"},
            {**self.spec, "spritesheetPath": str(self.root / "clip.png")},
            {**self.spec, "spritesheetPath": "missing.png"},
            {**self.spec, "frameCount": 0},
            {**self.spec, "durations": [100]},
            {**self.spec, "durations": [[5000, 100]] * 6},
            {**self.spec, "baseline": -1},
            {**self.spec, "frames": [{"rect": [340, 0, 120, 120]}] * 6},
        ]
        for spec in invalid_specs:
            with self.subTest(spec=spec), self.assertLogs("petpack", logging.WARNING):
                manifest = copy.deepcopy(self.manifest)
                manifest["animationClips"]["review"] = spec
                atlas = self.atlas(manifest)
            self.assertIn("review", atlas.clip_errors)
            self.assertEqual(set(atlas.clip_durations()), {"idle"})
            self.assertEqual(atlas.frames("review"), STATE_FRAMES["review"])
            self.assertEqual(atlas.cell_image("review", 0).pixelColor(0, 0), QColor(25, 50, 75))

    def test_empty_frame_falls_back_and_old_packages_still_work(self) -> None:
        empty = QImage(360, 240, QImage.Format.Format_RGBA8888)
        empty.fill(Qt.GlobalColor.transparent)
        empty.save(str(self.root / "empty.png"))
        self.manifest["animationClips"]["idle"]["spritesheetPath"] = "empty.png"
        with self.assertLogs("petpack", logging.WARNING):
            atlas = self.atlas()
        self.assertEqual(atlas.clip_durations(), {})
        del self.manifest["animationClips"]
        atlas = self.atlas()
        for state, count in STATE_FRAMES.items():
            self.assertEqual(atlas.frames(state), count)
            self.assertEqual(atlas.cell_image(state, count - 1).size(), QSize(192, 208))
        self.assertEqual(atlas.cell_image("missing", 0), atlas.cell_image("idle", 0))

    def test_renderer_resizes_once_for_actual_dpr_and_invalidates_cache(self) -> None:
        renderer = SpriteRenderer(PetPackage(self.root, self.manifest))
        renderer.configure(QSize(288, 312), 2.0, False)
        pixmap = renderer.pixmap("idle", 1)
        self.assertEqual(pixmap.size(), QSize(576, 624))
        self.assertEqual(pixmap.devicePixelRatio(), 2.0)
        self.assertIs(renderer.pixmap("idle", 1), pixmap)
        renderer.configure(QSize(192, 208), 1.0, False)
        self.assertEqual(renderer.pixmap("idle", 1).size(), QSize(192, 208))
        self.assertIsNot(renderer.pixmap("idle", 1), pixmap)

    def test_breath_timer_stops_for_hidden_dragged_and_reduced_motion(self) -> None:
        pet = PetWindow()
        self.addCleanup(pet.close)
        self.assertFalse(pet._motion_timer.isActive())
        pet.show()
        APP.processEvents()
        self.assertTrue(pet._motion_timer.isActive())
        pet.set_motion_enabled(False)
        self.assertFalse(pet._motion_timer.isActive())
        pet.set_motion_enabled(True)
        self.assertTrue(pet._motion_timer.isActive())
        pet._dragging = True
        pet._sync_motion()
        self.assertFalse(pet._motion_timer.isActive())
        pet._dragging = False
        pet._sync_motion()
        self.assertTrue(pet._motion_timer.isActive())
        pet.hide()
        self.assertFalse(pet._motion_timer.isActive())


if __name__ == "__main__":
    unittest.main(verbosity=2)
