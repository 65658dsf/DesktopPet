"""AI chat window: streaming bubbles, quick prompts, offline/online badge."""

from __future__ import annotations

from math import ceil

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QRegion,
                           QTextBlockFormat, QTextCursor, QTextOption)
from PySide6.QtWidgets import (QBoxLayout, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSizePolicy, QTextEdit, QVBoxLayout, QWidget)

from chat_controls import FlowLayout, GrowingTextEdit

DARK = "#141013"
CARD = "#1e181c"
PET_BUBBLE = "#231a1e"
USER_BUBBLE = "#5c1f27"
ACCENT = "#c2444f"
TEXT = "#f2e7ea"
MUTED = "#a08e95"

QUICK_PROMPTS = ["在忙什么？", "陪我聊会儿", "今天好累", "夸夸我", "有什么想说的"]


def avatar_portrait(pixmap: QPixmap) -> QPixmap:
    """Frame the visible character, without the animation cell's empty margins."""
    if pixmap.isNull():
        return QPixmap()
    bounds = QRegion(pixmap.mask()).boundingRect() if pixmap.hasAlphaChannel() else pixmap.rect()
    if bounds.isEmpty():
        return QPixmap()
    # Use the upper square for a readable face/shoulders portrait. Keep the
    # original atlas pixels; painting will scale them for the current screen.
    side = min(bounds.width(), bounds.height())
    portrait = pixmap.copy(bounds.x() + (bounds.width() - side) // 2,
                           bounds.y(), side, side)
    portrait.setDevicePixelRatio(1.0)
    return portrait


class Avatar(QWidget):
    def __init__(self, size: int, pixmap: QPixmap | None = None) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        self.setAccessibleName("宠物头像")
        self._portrait = pixmap if pixmap is not None else QPixmap()

    def set_portrait(self, pixmap: QPixmap) -> None:
        self._portrait = pixmap
        self.update()

    def paintEvent(self, event) -> None:                         # noqa: N802
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing |
                               QPainter.RenderHint.SmoothPixmapTransform)
        frame = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(QColor("#30232b"))
        painter.setPen(QPen(QColor("#4a333d"), 1))
        painter.drawRoundedRect(frame, 12, 12)
        if self._portrait.isNull():
            painter.setPen(QColor(TEXT))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "宠")
            return
        content = frame.adjusted(3, 3, -3, -3)
        clip = QPainterPath()
        clip.addRoundedRect(content, 9, 9)
        painter.setClipPath(clip)
        painter.drawPixmap(content, self._portrait, QRectF(self._portrait.rect()))


class MessageText(QTextEdit):
    """Selectable text that grows to its document, with no nested scrolling."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = ""
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFont(QFont("Microsoft YaHei UI", 11))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.setStyleSheet(
            f"QTextEdit {{ color: {TEXT}; background: transparent; border: none; padding: 0; }}"
            "QTextEdit > QWidget { background: transparent; border: none; }")
        self.document().setDocumentMargin(0)
        option = self.document().defaultTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDefaultTextOption(option)
        self.document().documentLayout().documentSizeChanged.connect(self._fit_height)
        self.setText(text)

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:                         # noqa: N802
        previous = self._text
        self._text = text
        if previous and text.startswith(previous):
            # Append streaming output without replacing the reader's selection.
            cursor = QTextCursor(self.document())
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text[len(previous):])
        else:
            self.setPlainText(text)
            cursor = QTextCursor(self.document())
            cursor.select(QTextCursor.SelectionType.Document)
            block = QTextBlockFormat()
            block.setLineHeight(145, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            block.setBottomMargin(6)
            cursor.mergeBlockFormat(block)
        metrics = self.fontMetrics()
        self.natural_width = max((metrics.horizontalAdvance(line.expandtabs(4))
                                  for line in text.splitlines()), default=0)
        self._fit_height()

    def _fit_height(self, _size=None) -> None:
        height = ceil(self.document().documentLayout().documentSize().height()) + 2
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event) -> None:                         # noqa: N802
        super().resizeEvent(event)
        self._fit_height()

    def wheelEvent(self, event) -> None:                          # noqa: N802
        # Let the conversation scroll, even while the pointer is over a reply.
        event.ignore()


class MessageBubble(QFrame):
    def __init__(self, role: str, text: str, avatar: QPixmap | None = None) -> None:
        super().__init__()
        self.role = role
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.label = MessageText(text)
        self._available_width = 1
        self._avatar_space = 0

        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)

        self.card = card = QFrame()
        card.setObjectName("messageCard")
        card.setStyleSheet(
            f"QFrame#messageCard {{ background: {PET_BUBBLE if role == 'assistant' else USER_BUBBLE};"
            f"border: 1px solid {'#4a2b33' if role == 'assistant' else ACCENT};"
            "border-radius: 10px; }")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.addWidget(self.label)

        if role == "assistant":
            if avatar is not None and not avatar.isNull():
                pic = Avatar(40, avatar)
                box.addWidget(pic, 0, Qt.AlignmentFlag.AlignTop)
                self._avatar_space = 48
            box.addWidget(card, 0, Qt.AlignmentFlag.AlignTop)
            box.addStretch(1)
        else:
            box.addStretch(1)
            box.addWidget(card, 0, Qt.AlignmentFlag.AlignTop)

    def set_available_width(self, width: int) -> None:
        self._available_width = max(1, width)
        available = max(1, self._available_width - self._avatar_space)
        limit = max(1, int(available * (0.92 if self.role == "assistant" else 0.84)))
        desired = max(48, self.label.natural_width + 32)
        self.card.setFixedWidth(min(desired, limit))

    def set_text(self, text: str) -> None:
        self.label.setText(text)
        self.set_available_width(self._available_width)


class ChatWindow(QWidget):
    send_requested = Signal(str)
    stop_requested = Signal()
    clear_requested = Signal()
    settings_requested = Signal()

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowTitle("秦彻 · 对话")
        self.resize(720, 720)
        self.setMinimumSize(400, 480)
        self.setFont(QFont("Microsoft YaHei UI", 10))
        self.setStyleSheet(f"QWidget {{ background: {DARK}; color: {TEXT}; }}")

        self._avatar: QPixmap | None = None
        self._streaming_bubble: MessageBubble | None = None
        self._following_bottom = True
        self._scrolling = False
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._follow_bottom)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ---- header ------------------------------------------------------
        header = QFrame()
        header.setObjectName("chatHeader")
        header.setStyleSheet(f"QFrame#chatHeader {{ background: {CARD}; border: none; border-radius: 10px; }}")
        self.header_layout = head = QBoxLayout(QBoxLayout.Direction.LeftToRight, header)
        head.setContentsMargins(12, 10, 12, 10)
        head.setSpacing(10)

        identity = QWidget()
        identity.setStyleSheet("background: transparent;")
        identity_row = QHBoxLayout(identity)
        identity_row.setContentsMargins(0, 0, 0, 0)
        identity_row.setSpacing(10)

        self.avatar_label = Avatar(48)
        identity_row.addWidget(self.avatar_label, 0, Qt.AlignmentFlag.AlignVCenter)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        name = QLabel("秦彻")
        name.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.Bold))
        name.setStyleSheet(f"color: {TEXT}; background: transparent;")
        self.status = QLabel("本地离线模式 · 完全离线运行")
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status.setStyleSheet(f"color: {MUTED}; background: transparent; font-size: 11px;")
        title_box.addWidget(name)
        title_box.addWidget(self.status)
        identity_row.addLayout(title_box, 1)
        head.addWidget(identity, 1)

        actions = QWidget()
        actions.setStyleSheet("background: transparent;")
        actions.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        actions_row = QHBoxLayout(actions)
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(8)

        self.mode_badge = QLabel("离线")
        self.mode_badge.setObjectName("modeBadge")
        self.mode_badge.setFixedSize(56, 32)
        self.mode_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        actions_row.addWidget(self.mode_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        settings_button = QPushButton("设置")
        clear_button = QPushButton("清空")
        for button, slot in ((settings_button, self.settings_requested.emit),
                             (clear_button, self.clear_requested.emit)):
            button.setFixedSize(64, 32)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ background: #2a2228; color: {TEXT}; border: 1px solid #43313a;"
                "border-radius: 8px; padding: 0; font-size: 12px; }"
                f"QPushButton:hover {{ background: #3a2c34; border-color: {ACCENT}; }}"
                "QPushButton:pressed { background: #4a2b35; border-color: #e27885; }"
                "QPushButton:focus { border-color: #e27885; }"
                "QPushButton:disabled { color: #75656c; background: #231c21; }")
            button.clicked.connect(slot)
            actions_row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(actions, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(header)
        self.set_mode(False, "")

        # ---- messages ----------------------------------------------------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { background: transparent; width: 8px; }"
            "QScrollBar::handle:vertical { background: #453039; border-radius: 4px; }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }")
        self.messages_host = QWidget()
        self.messages_host.setStyleSheet("background: transparent;")
        self.messages = QVBoxLayout(self.messages_host)
        self.messages.setContentsMargins(2, 2, 2, 2)
        self.messages.setSpacing(16)
        self.messages.addStretch(1)
        self.scroll.setWidget(self.messages_host)
        root.addWidget(self.scroll, 1)
        self.scroll.viewport().installEventFilter(self)
        bar = self.scroll.verticalScrollBar()
        bar.valueChanged.connect(self._on_scroll_changed)
        bar.rangeChanged.connect(lambda _low, _high: self._scroll_to_bottom())
        self.latest_button = QPushButton("回到最新", self.scroll.viewport())
        self.latest_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.latest_button.setStyleSheet(
            f"QPushButton {{ background: #3a2832; color: {TEXT}; border: 1px solid #72505f;"
            "border-radius: 14px; padding: 6px 14px; }"
            f"QPushButton:hover {{ border-color: {ACCENT}; background: #4b303b; }}")
        self.latest_button.clicked.connect(lambda: self._scroll_to_bottom(force=True))
        self.latest_button.hide()

        # ---- thinking row ------------------------------------------------
        self.thinking_row = QFrame()
        self.thinking_row.setStyleSheet("background: transparent;")
        think = QHBoxLayout(self.thinking_row)
        think.setContentsMargins(4, 0, 4, 0)
        self.thinking_label = QLabel("")
        self.thinking_label.setStyleSheet(f"color: {MUTED}; font-size: 11px; background: transparent;")
        think.addWidget(self.thinking_label)
        think.addStretch(1)
        self.stop_button = QPushButton("停止")
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_button.setStyleSheet(
            "QPushButton { background: #3a2027; color: #f0d7db; border: 1px solid #6d3039;"
            "border-radius: 7px; padding: 3px 12px; font-size: 11px; }")
        self.stop_button.clicked.connect(self.stop_requested.emit)
        think.addWidget(self.stop_button)
        self.thinking_row.hide()
        root.addWidget(self.thinking_row)

        # ---- quick prompts ----------------------------------------------
        chips_host = QWidget()
        chips = FlowLayout(chips_host, spacing=6)
        for prompt in QUICK_PROMPTS:
            chip = QPushButton(prompt)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                f"QPushButton {{ background: #221a1f; color: {MUTED}; border: 1px solid #3b2b33;"
                "border-radius: 12px; padding: 4px 12px; font-size: 11px; }"
                f"QPushButton:hover {{ color: {TEXT}; border-color: {ACCENT}; }}")
            chip.clicked.connect(lambda _=False, text=prompt: self._quick_send(text))
            chips.addWidget(chip)
        root.addWidget(chips_host)

        # ---- input -------------------------------------------------------
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.input = GrowingTextEdit()
        self.input.setPlaceholderText("说点什么……（Enter 发送 / Shift+Enter 换行）")
        self.input.setFont(QFont("Microsoft YaHei UI", 10))
        self.input.setStyleSheet(
            f"QTextEdit {{ background: {CARD}; color: {TEXT}; border: 1px solid #43313a;"
            "border-radius: 10px; padding: 6px; }"
            f"QTextEdit:focus {{ border-color: {ACCENT}; }}")
        self.input.installEventFilter(self)
        input_row.addWidget(self.input, 1)

        self.send_button = QPushButton("发送")
        self.send_button.setFixedSize(74, 74)
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))
        self.send_button.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: #1a1114; border: none;"
            "border-radius: 10px; }"
            "QPushButton:hover { background: #d5545f; }"
            "QPushButton:disabled { background: #4a3238; color: #8d757c; }")
        self.send_button.clicked.connect(self._emit_send)
        input_row.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(input_row)

    # ------------------------------------------------------------------ #
    def eventFilter(self, obj, event):                            # noqa: N802
        if obj is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._reflow_messages()
            if hasattr(self, "latest_button"):
                self._position_latest_button()
        if obj is getattr(self, "input", None) and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and \
                    not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self._emit_send()
                return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:                         # noqa: N802
        super().resizeEvent(event)
        narrow = self.width() < 540
        self.header_layout.setDirection(QBoxLayout.Direction.TopToBottom if narrow
                                        else QBoxLayout.Direction.LeftToRight)
        self.header_layout.setStretch(0, 0 if narrow else 1)

    def _reflow_messages(self) -> None:
        width = max(1, self.scroll.viewport().width() - 4)
        for index in range(self.messages.count() - 1):
            self.messages.itemAt(index).widget().set_available_width(width)

    def _position_latest_button(self) -> None:
        self.latest_button.adjustSize()
        self.latest_button.move(
            max(0, self.scroll.viewport().width() - self.latest_button.width() - 12),
            max(0, self.scroll.viewport().height() - self.latest_button.height() - 10))

    def _quick_send(self, text: str) -> None:
        self.input.setPlainText(text)
        self._emit_send()

    def _emit_send(self) -> None:
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self.send_requested.emit(text)

    # ------------------------------------------------------------------ #
    def set_avatar(self, pixmap: QPixmap) -> None:
        self._avatar = avatar_portrait(pixmap)
        self.avatar_label.set_portrait(self._avatar)
        for avatar in self.messages_host.findChildren(Avatar):
            avatar.set_portrait(self._avatar)

    def set_mode(self, online: bool, model: str) -> None:
        self.mode_badge.setText("在线" if online else "离线")
        self.mode_badge.setToolTip("已启用在线 AI" if online else "本地离线模式，不发起任何网络请求")
        foreground, background, border = ("#e2c07a", "#30291f", "#635035") if online else \
            ("#d9abb7", "#30232b", "#543740")
        self.mode_badge.setStyleSheet(
            f"QLabel#modeBadge {{ background: {background}; color: {foreground};"
            f"border: 1px solid {border}; border-radius: 8px; padding: 0; font-size: 11px; }}")
        if online:
            self.status.setText(f"OpenAI 兼容接口 · {model}")
        else:
            self.status.setText("本地离线模式 · 完全离线运行")
        self.status.setToolTip(self.status.text())

    def add_message(self, role: str, text: str) -> MessageBubble:
        bubble = MessageBubble(role, text, self._avatar if role == "assistant" else None)
        bubble.set_available_width(self.scroll.viewport().width() - 4)
        self.messages.insertWidget(self.messages.count() - 1, bubble)
        self._scroll_to_bottom(force=role == "user")
        return bubble

    def begin_stream(self, placeholder: str = "……") -> None:
        self._streaming_bubble = self.add_message("assistant", placeholder)
        self._stream_text = ""
        self.set_busy(True, "对方正在输入")
        self._scroll_to_bottom()

    def append_delta(self, piece: str) -> None:
        if self._streaming_bubble is None:
            self.begin_stream("")
        self._stream_text += piece
        self._streaming_bubble.set_text(self._stream_text)
        self._scroll_to_bottom()

    def finish_stream(self) -> str:
        text = getattr(self, "_stream_text", "")
        if self._streaming_bubble is not None and not text:
            self._streaming_bubble.set_text("（没有返回内容）")
        self._streaming_bubble = None
        self._stream_text = ""
        self.set_busy(False)
        return text

    def show_error(self, message: str) -> None:
        self._streaming_bubble = None
        self.set_busy(False)
        self.add_message("assistant", f"（连接失败：{message}）\n可以在「设置 → AI 接入」里检查接口，或切换回本地离线模式。")

    def set_busy(self, busy: bool, hint: str = "") -> None:
        self.thinking_row.setVisible(busy)
        self.thinking_label.setText(hint)
        self.send_button.setEnabled(not busy)

    def clear_messages(self) -> None:
        self._scroll_timer.stop()
        self._following_bottom = True
        self.latest_button.hide()
        while self.messages.count() > 1:
            item = self.messages.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._streaming_bubble = None
        self.set_busy(False)

    def _on_scroll_changed(self, value: int) -> None:
        if not self._scrolling:
            bar = self.scroll.verticalScrollBar()
            self._following_bottom = bar.maximum() - value <= 24
        self.latest_button.setVisible(not self._following_bottom)
        self.latest_button.raise_()

    def _scroll_to_bottom(self, *, force: bool = False) -> None:
        if force:
            self._following_bottom = True
            self.latest_button.hide()
        if self._following_bottom:
            self._scroll_timer.start(0)

    def _follow_bottom(self) -> None:
        if not self._following_bottom:
            return
        self._scrolling = True
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        self._scrolling = False

    def closeEvent(self, event) -> None:                          # noqa: N802
        event.ignore()
        self.hide()
