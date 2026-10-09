"""Grab the whole desktop (Qt-based, includes layered windows) into a PNG.

Usage: python capture_screen.py <output.png>
"""
import sys

from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
target = sys.argv[1] if len(sys.argv) > 1 else "screen.png"
shot = app.primaryScreen().grabWindow(0)
shot.save(target)
print("saved", target, shot.width(), "x", shot.height())