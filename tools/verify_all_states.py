"""Check the shipped action set and every Settings -> Preview path.

Runs offscreen with in-memory settings: no installed pets, credentials, registry
changes, or network requests. Run after exporting the compatibility atlas:
    .venv/Scripts/python.exe tools/verify_all_states.py
"""

from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageChops  # noqa: E402
from PySide6.QtCore import QSharedMemory, QSize, Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton, QTabWidget  # noqa: E402

import animation  # noqa: E402
import config  # noqa: E402
import main as pet_main  # noqa: E402
from petpack import Atlas, PetPackage, STATE_FRAMES, STATE_ROWS, _load_package  # noqa: E402
from pet_window import SpriteRenderer  # noqa: E402


def pixels(image: QImage) -> Image.Image:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes("RGBA", (image.width(), image.height()),
                           bytes(image.constBits()), "raw", "RGBA", image.bytesPerLine())


class MemoryConfig:
    def __init__(self) -> None:
        self.data = copy.deepcopy(config.DEFAULTS)
        self.data.update(showOnStartup=False, idleVariety=False, manualState="auto")

    def get(self, key, default=None):
        return self.data.get(key, default)

    def save(self) -> None:
        pass

    @property
    def ai(self):
        return self.data["ai"]


class ShippedActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.package = _load_package(ROOT / "pets" / "qinche-q")
        if cls.package is None:
            raise AssertionError("Cannot load shipped qinche-q package")
        cls.atlas = Atlas(cls.package, 1)

    def test_all_actions_have_distinct_visible_frames_within_the_canvas(self) -> None:
        self.assertEqual(self.atlas.clip_errors, {})
        clips = self.atlas.clip_durations()
        for state, count in {**STATE_FRAMES, "poke": 8}.items():
            with self.subTest(state=state):
                self.assertIn(state, clips, "Action is falling back to the old atlas")
                self.assertEqual(self.atlas.frames(state), count)
                fingerprints = set()
                for index in range(count):
                    frame = self.atlas.cell_image(state, index)
                    x, y, width, height = Atlas._alpha_bounds(frame)
                    self.assertGreater(x, 0, f"{state}[{index}] touches left edge")
                    self.assertGreater(y, 0, f"{state}[{index}] touches top edge")
                    self.assertLess(x + width, frame.width(), f"{state}[{index}] touches right edge")
                    self.assertLess(y + height, frame.height(), f"{state}[{index}] touches bottom edge")
                    fingerprints.add(hashlib.sha256(bytes(frame.constBits())).digest())
                self.assertGreater(len(fingerprints), 1, "Action has no visible frame changes")

    def test_every_frame_renders_at_standard_fractional_and_double_dpr(self) -> None:
        renderer = SpriteRenderer(self.package)
        for dpr in (1.0, 1.5, 2.0):
            renderer.configure(QSize(192, 208), dpr, False)
            self.assertEqual(renderer.atlas.clip_errors, {})
            for state in (*STATE_ROWS, "poke"):
                for index in range(renderer.atlas.frames(state)):
                    with self.subTest(dpr=dpr, state=state, frame=index):
                        frame = renderer.pixmap(state, index)
                        self.assertFalse(frame.isNull())
                        self.assertEqual(frame.size(), QSize(round(192 * dpr), round(208 * dpr)))
                        self.assertEqual(frame.devicePixelRatio(), dpr)
                        self.assertIsNotNone(pixels(frame.toImage()).getchannel("A").getbbox())

    def test_left_run_is_framewise_mirror_of_right_run_in_the_same_order(self) -> None:
        for index in range(STATE_FRAMES["running-right"]):
            with self.subTest(frame=index):
                right = self.atlas.cell_image("running-right", index)
                left = self.atlas.cell_image("running-left", index)
                right_crop = pixels(right.copy(*Atlas._alpha_bounds(right)))
                left_crop = pixels(left.copy(*Atlas._alpha_bounds(left)))
                self.assertEqual(left_crop.size, right_crop.size)
                mirrored = right_crop.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                self.assertIsNone(ImageChops.difference(left_crop.getchannel("A"),
                                                       mirrored.getchannel("A")).getbbox())
                # PNG assembly and Qt's premultiplication can round translucent
                # RGB by one visible level; shape and frame order must be exact.
                for background in ("black", "white"):
                    actual = Image.alpha_composite(Image.new("RGBA", left_crop.size, background),
                                                   left_crop)
                    expected = Image.alpha_composite(Image.new("RGBA", mirrored.size, background),
                                                     mirrored)
                    extrema = ImageChops.difference(actual, expected).getextrema()
                    self.assertLessEqual(max(upper for _lower, upper in extrema), 1)

    def test_jump_has_visible_rise_and_fall_relative_to_idle(self) -> None:
        idle = self.atlas.cell_image("idle", 0)
        _, y, _, height = Atlas._alpha_bounds(idle)
        idle_baseline = (y + height) * 208 / idle.height()
        baselines = []
        for index in range(self.atlas.frames("jumping")):
            frame = self.atlas.cell_image("jumping", index)
            _, y, _, height = Atlas._alpha_bounds(frame)
            baselines.append((y + height) * 208 / frame.height())
        self.assertGreaterEqual(max(baselines) - min(baselines), 12)
        self.assertLessEqual(min(baselines), idle_baseline - 12)
        self.assertLess(min(baselines), baselines[0])
        self.assertLess(min(baselines), baselines[-1])

    def test_compatibility_atlas_has_all_rows_and_transparent_unused_cells(self) -> None:
        self.assertEqual(sorted(self.package.available_scales()), [1, 2])
        self.assertEqual(self.package.manifest.get("sourceScale"), 2)
        self.assertNotIn("4x", self.package.manifest.get("spritesheets", {}),
                         "Do not advertise the obsolete affine 4x atlas")
        for state in self.atlas.clip_durations():
            for index in range(self.atlas.frames(state)):
                source = self.atlas.cell_image(state, index)
                self.assertGreaterEqual(source.width(), 384, f"{state}[{index}] would need 2x upscaling")
                self.assertGreaterEqual(source.height(), 416, f"{state}[{index}] would need 2x upscaling")
        manifest = copy.deepcopy(self.package.manifest)
        manifest.pop("animationClips", None)
        for scale in (1, 2):
            core = Atlas(PetPackage(self.package.root, manifest), scale)
            self.assertEqual(core.image.size(), QSize(1536 * scale, 1872 * scale))
            for row, state in enumerate(STATE_ROWS):
                for column in range(8):
                    with self.subTest(scale=scale, state=state, column=column):
                        frame = core.image.copy(column * 192 * scale, row * 208 * scale,
                                                192 * scale, 208 * scale)
                        bounds = pixels(frame).getchannel("A").getbbox()
                        if column < STATE_FRAMES[state]:
                            self.assertIsNotNone(bounds, "Compatibility action contains an empty frame")
                        else:
                            self.assertIsNone(bounds, "Unused compatibility cell is not transparent")

    def test_each_settings_preview_plays_two_cycles_then_returns_to_standby(self) -> None:
        replacements = [
            patch.object(pet_main, "Config", MemoryConfig),
            patch.object(pet_main, "scan_packages", return_value=[self.package]),
            patch.object(pet_main.PetApp, "_sync_autostart"),
            patch.object(pet_main.PetApp, "_say"),
            patch.object(pet_main.Tray, "show"),
        ]
        for replacement in replacements:
            replacement.start()
            self.addCleanup(replacement.stop)
        controller = pet_main.PetApp(self.app, QSharedMemory())
        self.addCleanup(self._close_controller, controller)
        controller.pet.show()
        controller.settings.show()
        tabs = controller.settings.findChild(QTabWidget)
        look_tab = next(index for index in range(tabs.count())
                        if tabs.tabText(index) == "桌宠外观")
        tabs.setCurrentIndex(look_tab)
        preview = next(button for button in controller.settings.findChildren(QPushButton)
                       if button.text() == "立即预览")
        self.app.processEvents()
        self.assertEqual(controller.renderer.atlas.clip_errors, {})
        frames: list[tuple[str, int]] = []
        finished: list[str] = []
        controller.animator.frame_changed.connect(lambda state, index: frames.append((state, index)))
        controller.animator.finished.connect(finished.append)
        for state in STATE_ROWS:
            with self.subTest(state=state):
                index = controller.settings.state_box.findData(state)
                self.assertGreaterEqual(index, 0)
                controller.settings.state_box.setCurrentIndex(index)
                frames.clear()
                finished.clear()
                QTest.mouseClick(preview, Qt.MouseButton.LeftButton)
                self.assertEqual(controller.animator.state, state)
                self.assertFalse(controller.pet._pixmap.isNull())
                for _ in range(STATE_FRAMES[state] * 2):
                    controller.animator._timer.stop()
                    deadline = controller.animator._deadline
                    self.assertIsNotNone(deadline)
                    with patch.object(animation, "monotonic", return_value=deadline):
                        controller.animator._tick()
                expected = [(state, frame) for frame in range(STATE_FRAMES[state])] * 2
                self.assertEqual(frames, expected + [("idle", 0)])
                self.assertEqual(finished, [state])
                self.assertEqual(controller.animator.state, "idle")

        controller.settings.state_box.setCurrentIndex(controller.settings.state_box.findData("auto"))
        QTest.mouseClick(preview, Qt.MouseButton.LeftButton)
        self.assertEqual(controller.animator.state, "idle")

    def _close_controller(self, controller) -> None:
        for timer in controller.findChildren(pet_main.QTimer):
            timer.stop()
        controller.tray.hide()
        for window in (controller.pet, controller.bubble, controller.chat, controller.settings):
            window.hide()
            window.deleteLater()
        controller.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main(verbosity=2)
