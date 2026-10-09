"""Check pet click/drag events without personal settings, tray, or an AI service."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QSignalSpy, QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pet_window import PetWindow  # noqa: E402


LEFT = Qt.MouseButton.LeftButton
RIGHT = Qt.MouseButton.RightButton
START = QPoint(20, 20)
END = QPoint(44, 28)


class PetInputChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.pet = PetWindow()
        self.pet.set_motion_enabled(False)
        self.pet.resize(100, 100)
        self.pet.move(100, 100)
        self.clicks = QSignalSpy(self.pet.clicked)
        self.double_clicks = QSignalSpy(self.pet.double_clicked)
        self.context_menus = QSignalSpy(self.pet.right_clicked)
        self.drag_moves = QSignalSpy(self.pet.drag_moved)
        self.drag_ends = QSignalSpy(self.pet.drag_finished)
        self.pet.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.pet.close()
        self.pet.deleteLater()
        self.app.processEvents()

    def test_single_click_is_immediate(self) -> None:
        QTest.mouseClick(self.pet, LEFT, pos=START)
        # No timer wait: the first touch should start its reaction immediately.
        self.assertEqual(self.clicks.count(), 1)
        self.assertEqual(self.double_clicks.count(), 0)

    def test_repeated_single_click_events_each_respond(self) -> None:
        for count in range(1, 4):
            QTest.mouseClick(self.pet, LEFT, pos=START)
            self.assertEqual(self.clicks.count(), count)

    def test_full_double_click_sequence_does_not_poke_on_last_release(self) -> None:
        # Qt's native sequence is press, release, double-click, release.
        # QTest.mouseDClick alone sends only the double-click event, so include
        # both surrounding releases to exercise the actual desktop sequence.
        QTest.mouseClick(self.pet, LEFT, pos=START)
        QTest.mouseDClick(self.pet, LEFT, pos=START)
        QTest.mouseRelease(self.pet, LEFT, pos=START)
        self.assertEqual(self.clicks.count(), 1)
        self.assertEqual(self.double_clicks.count(), 1)

    def test_double_click_without_initial_release_does_not_make_up_a_poke(self) -> None:
        QTest.mouseDClick(self.pet, LEFT, pos=START)
        QTest.mouseRelease(self.pet, LEFT, pos=START)
        self.assertEqual(self.clicks.count(), 0)
        self.assertEqual(self.double_clicks.count(), 1)

    def test_next_single_click_after_double_click_still_works(self) -> None:
        QTest.mouseDClick(self.pet, LEFT, pos=START)
        QTest.mouseRelease(self.pet, LEFT, pos=START)
        QTest.mouseClick(self.pet, LEFT, pos=START)
        self.assertEqual(self.clicks.count(), 1)

    def test_drag_moves_pet_without_poking(self) -> None:
        before = self.pet.pos()
        QTest.mousePress(self.pet, LEFT, pos=START)
        QTest.mouseMove(self.pet, END)
        QTest.mouseRelease(self.pet, LEFT, pos=END)
        self.assertNotEqual(self.pet.pos(), before)
        self.assertGreater(self.drag_moves.count(), 0)
        self.assertEqual(self.drag_ends.count(), 1)
        self.assertEqual(self.clicks.count(), 0)

    def test_tiny_pointer_motion_is_still_a_click(self) -> None:
        before = self.pet.pos()
        QTest.mousePress(self.pet, LEFT, pos=START)
        QTest.mouseMove(self.pet, START + QPoint(1, 1))
        QTest.mouseRelease(self.pet, LEFT, pos=START + QPoint(1, 1))
        self.assertEqual(self.pet.pos(), before)
        self.assertEqual(self.clicks.count(), 1)
        self.assertEqual(self.drag_ends.count(), 0)

    def test_locked_and_disabled_drag_preserve_touch_feedback(self) -> None:
        for locked, enabled in ((True, True), (False, False)):
            with self.subTest(locked=locked, drag_enabled=enabled):
                self.pet.set_locked(locked)
                self.pet.drag_enabled = enabled
                before = self.pet.pos()
                clicks_before = self.clicks.count()
                QTest.mousePress(self.pet, LEFT, pos=START)
                QTest.mouseMove(self.pet, END)
                QTest.mouseRelease(self.pet, LEFT, pos=END)
                self.assertEqual(self.pet.pos(), before)
                self.assertEqual(self.clicks.count(), clicks_before + 1)
                self.assertEqual(self.drag_moves.count(), 0)

    def test_right_click_cancels_unfinished_left_press(self) -> None:
        QTest.mousePress(self.pet, LEFT, pos=START)
        QTest.mouseClick(self.pet, RIGHT, pos=START)
        QTest.mouseRelease(self.pet, LEFT, pos=START)
        self.assertEqual(self.context_menus.count(), 1)
        self.assertEqual(self.clicks.count(), 0)

    def test_hide_cancels_unfinished_left_press(self) -> None:
        QTest.mousePress(self.pet, LEFT, pos=START)
        self.pet.hide()
        self.pet.show()
        QTest.mouseRelease(self.pet, LEFT, pos=START)
        self.assertEqual(self.clicks.count(), 0)
        QTest.mouseClick(self.pet, LEFT, pos=START)
        self.assertEqual(self.clicks.count(), 1)

    def test_click_through_cancels_unfinished_left_press(self) -> None:
        QTest.mousePress(self.pet, LEFT, pos=START)
        self.pet.set_click_through(True)
        self.pet.set_click_through(False)
        QTest.mouseRelease(self.pet, LEFT, pos=START)
        self.assertEqual(self.clicks.count(), 0)
        QTest.mouseClick(self.pet, LEFT, pos=START)
        self.assertEqual(self.clicks.count(), 1)

    def test_interrupted_drag_finishes_once_without_a_poke(self) -> None:
        QTest.mousePress(self.pet, LEFT, pos=START)
        QTest.mouseMove(self.pet, END)
        self.pet.hide()
        self.pet.show()
        QTest.mouseRelease(self.pet, LEFT, pos=END)
        self.assertEqual(self.drag_ends.count(), 1)
        self.assertEqual(self.clicks.count(), 0)

    def test_release_without_press_is_ignored(self) -> None:
        QTest.mouseRelease(self.pet, LEFT, pos=START)
        self.assertEqual(self.clicks.count(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
