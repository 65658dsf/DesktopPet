"""The pet window: transparent, borderless, always-on-top, taskbar-skipped,
draggable when unlocked — plus the speech bubble overlay."""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Iterable

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

from petpack import Atlas, PetPackage


class SpriteRenderer:
    """Caches atlas or native-resolution clip frames at the window's actual DPR."""

    CACHE_LIMIT_BYTES = 64 * 1024 * 1024

    def __init__(self, package: PetPackage) -> None:
        self.package = package
        self.atlas: Atlas | None = None
        self.scale = 0
        self.size = QSize(192, 208)
        self.dpr = 1.0
        self.pixelated = False
        self._cache: OrderedDict[tuple[str, int], QPixmap] = OrderedDict()
        self._cache_bytes = 0

    def _clear_cache(self) -> None:
        self._cache.clear()
        self._cache_bytes = 0

    def configure(self, size: QSize, dpr: float, pixelated: bool) -> bool:
        """Returns True when the atlas was (re)loaded."""
        cw, ch = self.package.cell
        required = max(size.width() / cw, size.height() / ch) * max(1.0, dpr)
        scale = self.package.choose_scale(required)
        reloaded = False
        if self.atlas is None or scale != self.scale:
            self.atlas = Atlas(self.package, scale)
            self.scale = scale
            self._clear_cache()
            reloaded = True
        if (size != self.size or abs(dpr - self.dpr) > 1e-3 or pixelated != self.pixelated):
            self.size = size
            self.dpr = dpr
            self.pixelated = pixelated
            self._clear_cache()
        return reloaded

    def pixmap(self, state: str, index: int) -> QPixmap:
        key = (state, index)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        if self.atlas is None:
            return QPixmap()
        image = self.atlas.cell_image(state, index)
        pixmap = QPixmap.fromImage(image)
        target = QSize(max(1, round(self.size.width() * self.dpr)),
                       max(1, round(self.size.height() * self.dpr)))
        mode = Qt.TransformationMode.FastTransformation if self.pixelated \
            else Qt.TransformationMode.SmoothTransformation
        scaled = pixmap.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, mode)
        scaled.setDevicePixelRatio(self.dpr)
        frame_bytes = scaled.width() * scaled.height() * 4
        if frame_bytes <= self.CACHE_LIMIT_BYTES:
            while self._cache and self._cache_bytes + frame_bytes > self.CACHE_LIMIT_BYTES:
                _old_key, old_frame = self._cache.popitem(last=False)
                self._cache_bytes -= old_frame.width() * old_frame.height() * 4
            self._cache[key] = scaled
            self._cache_bytes += frame_bytes
        return scaled

    def prepare_frames(self, states: Iterable[str], max_bytes: int = 64 * 1024 * 1024) -> None:
        """Warm action frames, keeping speculative cache use inside a memory budget."""
        if self.atlas is None:
            return
        budget = min(max_bytes, self.CACHE_LIMIT_BYTES)
        frame_bytes = (max(1, round(self.size.width() * self.dpr))
                       * max(1, round(self.size.height() * self.dpr)) * 4)
        counts = {state: self.atlas.frames(state) for state in dict.fromkeys(states)}
        # Get every action ready to start before filling its later poses. This
        # matters on large displays, where the budget may fit only a few cycles.
        for index in range(max(counts.values(), default=0)):
            for state, count in counts.items():
                if index >= count:
                    continue
                if (state, index) in self._cache:
                    continue
                if self._cache_bytes + frame_bytes > budget:
                    return
                self.pixmap(state, index)


class PetWindow(QWidget):
    clicked = Signal()
    double_clicked = Signal()
    right_clicked = Signal(QPoint)
    drag_moved = Signal(str)
    drag_finished = Signal()
    moved = Signal(QPoint)

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowTitle("秦彻 · 桌面宠物")
        self.drag_enabled = True
        self.locked = False
        self._pixmap = QPixmap()
        self._press_global: QPoint | None = None
        self._press_pos = QPoint()
        self._dragging = False
        self._drag_direction = ""
        self._motion_enabled = True
        self._transitions_enabled = True
        self._motion_elapsed = 0
        self._motion_clock = QElapsedTimer()
        self._transition_clock = QElapsedTimer()
        self._transition_duration = 0
        self._transition_from = QPixmap()
        self._transition_target = QPixmap()
        self._motion_timer = QTimer(self)
        self._motion_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._motion_timer.setInterval(16)
        self._motion_timer.timeout.connect(self._render_tick)

    # -- rendering ---------------------------------------------------------
    def set_frame(self, pixmap: QPixmap, transition_ms: int = 0) -> None:
        target = self._transition_target if self._transition_clock.isValid() else self._pixmap
        if pixmap.cacheKey() == target.cacheKey():
            return
        can_transition = (transition_ms > 0 and self._transitions_enabled
                          and self.isVisible() and not self._dragging
                          and not self._pixmap.isNull() and not pixmap.isNull()
                          and self._pixmap.size() == pixmap.size()
                          and abs(self._pixmap.devicePixelRatio() - pixmap.devicePixelRatio()) < 1e-3)
        if can_transition:
            # A new action may interrupt a blend. Continue from the visible pose,
            # not from either keyframe, so the interruption cannot jump backwards.
            self._advance_transition()
            self._transition_from = self._pixmap
            self._transition_target = pixmap
            self._transition_duration = max(1, int(transition_ms))
            self._transition_clock.start()
        else:
            self._finish_transition()
            self._pixmap = pixmap
        self._sync_motion()

    @staticmethod
    def _blend_frames(previous: QPixmap, target: QPixmap, progress: float) -> QPixmap:
        """Interpolate premultiplied color AND alpha, without source-over dimming."""
        if progress <= 0:
            return previous
        if progress >= 1:
            return target
        canvas = QImage(target.size(), QImage.Format.Format_ARGB32_Premultiplied)
        canvas.setDevicePixelRatio(target.devicePixelRatio())
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.setOpacity(1.0 - progress)
        painter.drawPixmap(0, 0, previous)

        # Plus combined with global opacity can attenuate the existing alpha in
        # Qt's raster engine. Weight the second source separately, then add it
        # at full opacity to preserve old * (1-t) + new * t in every channel.
        incoming = QImage(target.size(), QImage.Format.Format_ARGB32_Premultiplied)
        incoming.setDevicePixelRatio(target.devicePixelRatio())
        incoming.fill(Qt.GlobalColor.transparent)
        incoming_painter = QPainter(incoming)
        incoming_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        incoming_painter.setOpacity(progress)
        incoming_painter.drawPixmap(0, 0, target)
        incoming_painter.end()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setOpacity(1.0)
        painter.drawImage(0, 0, incoming)
        painter.end()
        return QPixmap.fromImage(canvas)

    def _advance_transition(self) -> None:
        if not self._transition_clock.isValid():
            return
        progress = min(1.0, self._transition_clock.elapsed() / self._transition_duration)
        if progress >= 1:
            self._finish_transition()
            return
        # Smooth endpoints remove the sudden onset/stop of a short pose change.
        progress = progress * progress * (3.0 - 2.0 * progress)
        self._pixmap = self._blend_frames(self._transition_from, self._transition_target, progress)

    def _finish_transition(self) -> None:
        if self._transition_clock.isValid():
            self._pixmap = self._transition_target
        self._transition_clock.invalidate()
        self._transition_duration = 0
        self._transition_from = QPixmap()
        self._transition_target = QPixmap()

    def _render_tick(self) -> None:
        self._advance_transition()
        self._sync_motion()

    def paintEvent(self, event) -> None:                          # noqa: N802
        if self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if self._motion_enabled and not self._dragging:
            elapsed = self._motion_elapsed
            if self._motion_clock.isValid():
                elapsed += self._motion_clock.elapsed()
            painter.translate(0, 0.6 * math.sin(elapsed * math.tau / 4000))
        painter.drawPixmap(0, 0, self._pixmap)

    def set_motion_enabled(self, enabled: bool) -> None:
        """Enable resting breath independently of transitions in other actions."""
        enabled = bool(enabled)
        if self._motion_enabled != enabled:
            self._motion_enabled = enabled
            if not enabled:
                self._motion_elapsed = 0
            self._sync_motion()

    def set_transitions_enabled(self, enabled: bool) -> None:
        """Reduced motion disables blends as well as animation scheduling."""
        self._transitions_enabled = bool(enabled)
        self._sync_motion()

    def _sync_motion(self) -> None:
        visible = self.isVisible() and not self._dragging
        if not visible or not self._transitions_enabled:
            self._finish_transition()
        breath_active = self._motion_enabled and visible
        if breath_active and not self._motion_clock.isValid():
            self._motion_clock.start()
        elif not breath_active and self._motion_clock.isValid():
            if self._motion_enabled:
                self._motion_elapsed = (self._motion_elapsed + self._motion_clock.elapsed()) % 4000
            self._motion_clock.invalidate()
        active = visible and (breath_active or self._transition_clock.isValid())
        if active and not self._motion_timer.isActive():
            self._motion_timer.start()
        elif not active:
            self._motion_timer.stop()
        self.update()

    def showEvent(self, event) -> None:                           # noqa: N802
        super().showEvent(event)
        self._sync_motion()

    def hideEvent(self, event) -> None:                           # noqa: N802
        self._cancel_pointer_gesture()
        self._sync_motion()
        super().hideEvent(event)

    # -- behaviour flags ---------------------------------------------------
    def set_always_on_top(self, on: bool) -> None:
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        if visible:
            self.show()

    def set_click_through(self, on: bool) -> None:
        if on:
            self._cancel_pointer_gesture()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, on)

    def set_locked(self, on: bool) -> None:
        self.locked = on

    # -- mouse -------------------------------------------------------------
    def _cancel_pointer_gesture(self) -> None:
        """Cancel an interrupted press so a late release cannot poke the pet."""
        was_dragging = self._dragging
        self._press_global = None
        self._dragging = False
        self._drag_direction = ""
        if was_dragging:
            self.drag_finished.emit()
            self._sync_motion()

    def mousePressEvent(self, event) -> None:                     # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_pos = self.pos()
            self._dragging = False
            self._drag_direction = ""
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._cancel_pointer_gesture()
            self.right_clicked.emit(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event) -> None:                      # noqa: N802
        if self._press_global is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self.drag_enabled or self.locked:
            return
        current = event.globalPosition().toPoint()
        delta = current - self._press_global
        if not self._dragging and abs(delta.x()) + abs(delta.y()) >= 4:
            self._dragging = True
            self._sync_motion()
        if not self._dragging:
            return
        self.move(self._press_pos + delta)
        self.moved.emit(self.pos())
        direction = "right" if delta.x() > 0 else "left"
        if direction != self._drag_direction:
            self._drag_direction = direction
            self.drag_moved.emit(direction)

    def mouseReleaseEvent(self, event) -> None:                   # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._press_global is None:
            # Qt delivers another release after mouseDoubleClickEvent. Its
            # press belongs to opening chat, not to another single-click poke.
            event.accept()
            return
        if self._dragging:
            self.drag_finished.emit()
            self.moved.emit(self.pos())
        else:
            self.clicked.emit()
        self._press_global = None
        self._dragging = False
        self._sync_motion()

    def mouseDoubleClickEvent(self, event) -> None:               # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._press_global = None
            self._sync_motion()
            self.double_clicked.emit()
            event.accept()


class Bubble(QWidget):
    """Small click-through overlay above the pet, styled after 秦彻's palette."""

    MAX_WIDTH = 240

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool
                            | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._text = ""
        self._font = QFont("Microsoft YaHei UI", 10)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_text(self, text: str, seconds: float = 6.0, anchor: QRect | None = None) -> None:
        self._text = text.strip()
        if not self._text:
            return
        metrics = QFontMetrics(self._font)
        rect = metrics.boundingRect(QRect(0, 0, self.MAX_WIDTH, 1000),
                                    Qt.TextFlag.TextWordWrap, self._text)
        width = max(72, rect.width() + 26)
        height = rect.height() + 20
        self.resize(width, height)
        if anchor is not None:
            self.place(anchor)
        self.show()
        self.raise_()
        self.update()
        self._timer.start(max(1000, int(seconds * 1000)))

    def place(self, anchor: QRect) -> None:
        screen = self.screen().availableGeometry() if self.screen() else None
        x = anchor.center().x() - self.width() // 2
        y = anchor.top() - self.height() - 10
        if screen is not None:
            x = max(screen.left() + 4, min(x, screen.right() - self.width() - 4))
            if y < screen.top() + 4:
                y = anchor.bottom() + 10
        self.move(x, y)

    def paintEvent(self, event) -> None:                          # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        body = QRect(0, 0, self.width(), self.height() - 8)

        path = QPainterPath()
        path.addRoundedRect(body.adjusted(1, 1, -1, -1), 12, 12)
        tail = QPainterPath()
        cx = self.width() / 2
        tail.moveTo(cx - 7, body.bottom() - 2)
        tail.lineTo(cx, body.bottom() + 7)
        tail.lineTo(cx + 7, body.bottom() - 2)
        tail.closeSubpath()
        path = path.united(tail)

        painter.setPen(QColor(163, 51, 64, 235))
        painter.setBrush(QColor(26, 18, 21, 238))
        painter.drawPath(path)

        painter.setPen(QColor(244, 231, 234))
        painter.setFont(self._font)
        painter.drawText(QRect(13, 6, self.width() - 26, self.height() - 20),
                         int(Qt.TextFlag.TextWordWrap.value), self._text)
