"""Exercise the actual chat widgets offscreen, without loading user settings.

Run with the project's Python: tools/verify_chat_layout.py --all-scales.
Each scale starts a separate Qt process because DPI settings precede QApplication.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback


def verify(scale: str) -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = scale
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtGui import QColor, QFontDatabase, QPixmap, QTextCursor
    from PySide6.QtWidgets import QApplication, QPushButton

    from chat_window import ChatWindow, QUICK_PROMPTS

    callback_errors: list[str] = []

    def record_callback_error(exc_type, exc, tb) -> None:
        callback_errors.append("".join(traceback.format_exception(exc_type, exc, tb)))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = record_callback_error
    app = QApplication([])
    for font_path in (Path("C:/Windows/Fonts/msyh.ttc"),
                      Path("C:/Windows/Fonts/msyhbd.ttc"),
                      Path("C:/Windows/Fonts/segoeui.ttf")):
        if font_path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id < 0:
                raise RuntimeError(f"Could not load installed test font: {font_path}")
    window = ChatWindow()
    avatar = QPixmap(80, 80)
    avatar.fill(QColor("#5c1f27"))
    window.set_avatar(avatar)
    window.show()  # QT_QPA_PLATFORM=offscreen never opens a desktop window.

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(message)

    def snapshot() -> tuple:
        bar = window.scroll.verticalScrollBar()
        rows = tuple((window.messages.itemAt(i).widget().size().toTuple(),
                      window.messages.itemAt(i).widget().card.size().toTuple())
                     for i in range(window.messages.count() - 1))
        return (window.size().toTuple(), window.scroll.viewport().size().toTuple(),
                window.input.size().toTuple(), bar.value(), bar.maximum(), rows)

    def settle() -> None:
        previous = None
        unchanged = 0
        for iteration in range(100):
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            require(not callback_errors, "Qt callback failed:\n" + "\n".join(callback_errors))
            state = snapshot()
            unchanged = unchanged + 1 if state == previous else 0
            previous = state
            if iteration >= 12 and unchanged >= 6:
                return
        raise AssertionError(f"Layout did not settle (possible oscillation): {previous}")

    def assert_complete(bubble, text: str) -> int:
        label = bubble.label
        document = label.document()
        require(label.text() == text, "Message text() was truncated or transformed")
        require(label.toPlainText() == text, "Rendered document differs from the full message")
        require(label.verticalScrollBar().maximum() == 0,
                "Message needs an internal vertical scrollbar")
        require(label.horizontalScrollBar().maximum() == 0,
                "Message needs an internal horizontal scrollbar")
        require(document.size().height() <= label.viewport().height() + 1,
                "The message document is taller than its visible viewport")
        require(window.scroll.horizontalScrollBar().maximum() == 0,
                "Conversation content overflows horizontally")
        require(bubble.width() <= window.scroll.viewport().width(),
                "Message row is wider than the conversation viewport")
        require(bubble.card.geometry().right() < bubble.width(),
                "Message card is clipped by its row")
        require(bubble.card.height() <= bubble.height(), "Message row clips its card")
        total_lines = 0
        block = document.firstBlock()
        while block.isValid():
            layout = block.layout()
            require(layout.lineCount() > 0, "A text block has not been laid out")
            covered = 0
            for index in range(layout.lineCount()):
                line = layout.lineAt(index)
                require(line.textStart() == covered, "Wrapped text has a gap")
                covered += line.textLength()
                require(line.naturalTextWidth() <= label.viewport().width() + 1,
                        "A line extends beyond the visible message width")
            require(covered == len(block.text()), "A text block ends before all its text is laid out")
            total_lines += layout.lineCount()
            block = block.next()
        return total_lines

    report: dict = {"scale": scale, "device_pixel_ratio": window.devicePixelRatioF()}
    chinese = "这是一段完整的中文回复，用来检查窗口缩放时文字自然换行并且没有丢失。" * 45
    chinese += "完整内容测试。" * 80
    require(len(chinese) >= 2000, "The long-message fixture must cover at least 2000 characters")
    paragraphs = "第一段：保留完整内容。\n\n" + chinese[:500] + "\n\n第二段：" + chinese[500:]
    url = "https://example.com/" + "abcdefghij0123456789" * 80
    fixtures = {"short": "你好，今天过得怎么样？", "chinese": chinese,
                "paragraphs": paragraphs, "long_url": url}
    measurements = {}
    for name, text in fixtures.items():
        window.clear_messages()
        bubble = window.add_message("assistant", text)
        by_width = []
        for width in (400, 720, 1100, 400):
            window.resize(width, 720)
            settle()
            lines = assert_complete(bubble, text)
            by_width.append({"window": width, "card_width": bubble.card.width(),
                             "card_height": bubble.card.height(), "lines": lines})
            if name == "short":
                require(lines == 1, f"Short reply wraps at window width {width}")
        if name != "short":
            require(by_width[0]["card_width"] < by_width[1]["card_width"] < by_width[2]["card_width"],
                    f"{name}: long message does not grow with the window")
            require(by_width[0]["card_height"] > by_width[1]["card_height"] > by_width[2]["card_height"],
                    f"{name}: wrapping does not reduce height when the window grows")
            require(by_width[0] == by_width[3], f"{name}: resizing back changes the settled layout")
        measurements[name] = by_width
    report["messages"] = measurements

    # User messages obey the same full-content contract on the opposite side.
    window.clear_messages()
    user_bubble = window.add_message("user", url)
    settle()
    assert_complete(user_bubble, url)

    # Appending text must retain a reader's text selection and the entire message.
    window.clear_messages()
    selected = window.add_message("assistant", "可以选中这些文字。")
    settle()
    cursor = selected.label.textCursor()
    cursor.setPosition(0)
    cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 5)
    selected.label.setTextCursor(cursor)
    selection = selected.label.textCursor().selectedText()
    selected.set_text("可以选中这些文字。这里是之后到达的内容。")
    settle()
    require(selected.label.textCursor().selectedText() == selection,
            "Streaming append destroyed the reader's selection")
    assert_complete(selected, "可以选中这些文字。这里是之后到达的内容。")

    # Populate enough history to exercise real QScrollArea ranges.
    window.clear_messages()
    window.resize(720, 720)
    for index in range(8):
        window.add_message("assistant", f"第{index + 1}条历史消息。" + chinese[:250])
    window.begin_stream("")
    window.append_delta(chinese[:300])
    settle()
    bar = window.scroll.verticalScrollBar()
    require(bar.maximum() > 500, "History did not create a scrollable conversation")
    require(bar.value() == bar.maximum(), "Initial stream does not follow the bottom")
    history_position = bar.maximum() // 3
    bar.setValue(history_position)
    settle()
    require(window.latest_button.isVisible(), "Reading history does not expose Return to latest")
    for piece in (chinese[:180], "\n\n" + url[:300], chinese[:180]):
        window.append_delta(piece)
        settle()
        require(bar.value() == history_position,
                "Streaming moved the reader away from the historical scroll position")
    window.latest_button.click()
    settle()
    require(bar.value() == bar.maximum(), "Return to latest did not restore the bottom")
    require(not window.latest_button.isVisible(), "Return to latest remains over the newest message")
    window.append_delta(chinese[:250])
    settle()
    require(bar.value() == bar.maximum(), "Streaming no longer follows after Return to latest")

    # A previously queued follow callback must not override a new scroll gesture.
    window.append_delta(chinese[:250])
    history_position = bar.maximum() // 2
    bar.setValue(history_position)
    settle()
    require(bar.value() == history_position, "A queued follow callback overrode manual scrolling")
    expected = window._stream_text
    require(window.finish_stream() == expected, "Finishing a stream changed its full text")
    settle()
    report["streaming"] = "history preserved; latest resumes follow; queued follow cancelled"

    window.clear_messages()
    settle()
    require(bar.maximum() == 0 and bar.value() == 0, "Clearing messages left stale scrolling")
    require(not window.latest_button.isVisible(), "Clearing messages left Return to latest visible")

    # Input uses a single outer height cap and then allows intentional input scrolling.
    window.input.setPlainText("输入内容保持完整，增加足够多的行。\n" * 80)
    settle()
    require(window.input.height() == window.input._maximum_input_height,
            "Long input did not stop at its maximum height")
    require(window.input.verticalScrollBar().maximum() > 0,
            "Capped input cannot scroll to its remaining text")
    maximum_input_height = window.input.height()
    window.input.clear()
    settle()
    require(window.input.height() == window.input._minimum_input_height,
            "Cleared input did not shrink to its default height")
    require(window.input.verticalScrollBar().maximum() == 0,
            "Cleared input retained an unnecessary scrollbar")
    report["input"] = {"empty_height": window.input.height(), "maximum_height": maximum_input_height}

    chips = [button for button in window.findChildren(QPushButton) if button.text() in QUICK_PROMPTS]
    require(len(chips) == len(QUICK_PROMPTS), "A quick-prompt button is missing")
    chip_rows = {}
    for width in (400, 720, 1100):
        window.resize(width, 720)
        settle()
        rows = set()
        for button in chips:
            require(button.parentWidget().rect().contains(button.geometry()),
                    f"Quick prompt is clipped at width {width}: {button.text()}")
            rows.add(button.y())
        chip_rows[width] = len(rows)
    require(chip_rows[400] >= 2, "Quick prompts do not wrap on a narrow window")
    require(chip_rows[720] == chip_rows[1100] == 1, "Quick prompts do not return to one row")
    report["quick_prompt_rows"] = chip_rows
    require(not callback_errors, "Qt callback failed:\n" + "\n".join(callback_errors))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"PASS: responsive chat layout at {float(scale) * 100:g}% scale")
    window.hide()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", choices=("1", "1.5", "2"), default="1")
    parser.add_argument("--all-scales", action="store_true")
    args = parser.parse_args()
    if args.all_scales:
        for scale in ("1", "1.5", "2"):
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--scale", scale], check=True)
    else:
        verify(args.scale)


if __name__ == "__main__":
    main()
