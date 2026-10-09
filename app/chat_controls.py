"""Small responsive layout and input controls used by the chat window."""

from __future__ import annotations

from math import ceil

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QTextEdit, QWidget


class FlowLayout(QLayout):
    """Place items left to right, wrapping onto as many rows as they need."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item: QLayoutItem) -> None:                 # noqa: N802
        self._items.append(item)
        self.invalidate()

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:           # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:           # noqa: N802
        if 0 <= index < len(self._items):
            item = self._items.pop(index)
            self.invalidate()
            return item
        return None

    def expandingDirections(self) -> Qt.Orientation:            # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:                         # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:                 # noqa: N802
        return self._arrange(QRect(0, 0, width, 0), measure_only=True)

    def setGeometry(self, rect: QRect) -> None:                  # noqa: N802
        super().setGeometry(rect)
        self._arrange(rect, measure_only=False)

    def sizeHint(self) -> QSize:                                # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:                             # noqa: N802
        size = QSize(0, 0)
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        return size + QSize(left + right, top + bottom)

    def _arrange(self, rect: QRect, *, measure_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        area = rect.adjusted(left, top, -right, -bottom)
        x, y = area.x(), area.y()
        row_height = 0
        gap = max(0, self.spacing())
        for item in self._items:
            if item.isEmpty():
                continue
            size = item.sizeHint().expandedTo(item.minimumSize())
            if row_height and x + size.width() > area.x() + area.width():
                x = area.x()
                y += row_height + gap
                row_height = 0
            if not measure_only:
                item.setGeometry(QRect(QPoint(x, y), size))
            x += size.width() + gap
            row_height = max(row_height, size.height())
        return y - rect.y() + row_height + bottom


class GrowingTextEdit(QTextEdit):
    """Grow with wrapped content, then scroll once the height limit is reached.

    Heights are Qt logical pixels. Keyboard handling stays with QTextEdit so
    callers can keep using an event filter for Enter/Shift+Enter behavior.
    """

    def __init__(self, parent: QWidget | None = None,
                 minimum_height: int = 74, maximum_height: int = 160) -> None:
        super().__init__(parent)
        self._minimum_input_height = max(1, minimum_height)
        self._maximum_input_height = max(self._minimum_input_height, maximum_height)
        self._height_update_pending = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFixedHeight(self._minimum_input_height)
        self.textChanged.connect(self._schedule_height_update)
        self.document().documentLayout().documentSizeChanged.connect(self._schedule_height_update)
        self._schedule_height_update()

    def _schedule_height_update(self, *_args) -> None:
        if not self._height_update_pending:
            self._height_update_pending = True
            QTimer.singleShot(0, self._update_height)

    def _update_height(self) -> None:
        self._height_update_pending = False
        # The actual viewport accounts for stylesheet padding and frame width;
        # documentSize includes wrapped lines and the document's own margins.
        chrome_height = self.height() - self.viewport().height()
        content_height = ceil(self.document().documentLayout().documentSize().height())
        height = min(self._maximum_input_height,
                     max(self._minimum_input_height, content_height + chrome_height))
        if height != self.height():
            self.setFixedHeight(height)
            self.updateGeometry()

    def resizeEvent(self, event) -> None:                        # noqa: N802
        super().resizeEvent(event)
        self._schedule_height_update()

    def changeEvent(self, event) -> None:                        # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.ApplicationFontChange,
                            QEvent.Type.StyleChange, QEvent.Type.ContentsRectChange):
            if hasattr(self, "_height_update_pending"):
                self._schedule_height_update()
