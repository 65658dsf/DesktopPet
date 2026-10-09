"""End-to-end check of the online AI path.

Usage:
  python tools/verify_ai.py                          # local mock server (default)
  python tools/verify_ai.py --base-url https://.../v1 --api-key sk-xxx --model deepseek-chat

Writes a log + screenshots into tools/gen_pet/out/ and restores the previous AI
settings before quitting (the test endpoint is never persisted).
"""

import argparse
import copy
import sys
from pathlib import Path

APP = Path(r"d:\Coding\DesktopPet\app")
TOOLS = Path(r"d:\Coding\DesktopPet\tools")
OUT = Path(r"d:\Coding\DesktopPet\tools\gen_pet\out")
LOG = OUT / "verify_ai.log"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(TOOLS))

from PySide6.QtCore import QSharedMemory, Qt, QTimer          # noqa: E402
from PySide6.QtWidgets import QApplication                    # noqa: E402

import main as app_main                                       # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8765/v1")
parser.add_argument("--api-key", default="mock-key")
parser.add_argument("--model", default="mock-model")
parser.add_argument("--prompt", default="用一句话夸夸我，要短")
args = parser.parse_args()

state = {"deltas": 0, "text": "", "error": ""}


def note(message: str) -> None:
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")
        handle.flush()


LOG.write_text("ai verify start\n", encoding="utf-8")
server = None
if "127.0.0.1" in args.base_url:
    import mock_openai

    server = mock_openai.start(8765)
    note("local mock server started")

QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
app.setApplicationName("秦彻 · 桌面宠物 (ai verify)")
app.setQuitOnLastWindowClosed(False)
shared = QSharedMemory("qinche-ai-verify-instance")
shared.create(1)

controller = app_main.PetApp(app, shared)
original_ai = copy.deepcopy(controller.config.data["ai"])
original_history = list(controller._history)
controller.config.data["ai"].update({
    "mode": "online",
    "baseUrl": args.base_url,
    "apiKey": args.api_key,
    "model": args.model,
    "stream": True,
})
controller._apply_settings(controller.config.data)
note(f"endpoint: {args.base_url} | model: {args.model}")
note("mode badge: " + controller.chat.mode_badge.text() + " | " + controller.chat.status.text())


def on_delta(piece: str) -> None:
    state["deltas"] += 1
    state["text"] += piece


def on_error(message: str) -> None:
    state["error"] = message


controller.llm.delta.connect(on_delta)
controller.llm.error.connect(on_error)


def send() -> None:
    controller.open_chat()
    controller._on_send(args.prompt)
    note("sent: " + args.prompt)


def mid_shot() -> None:
    note(f"mid-stream deltas={state['deltas']} text={state['text']!r} "
         f"pet={controller.animator.state}")
    app.primaryScreen().grabWindow(0).save(str(OUT / "v8_ai_streaming.png"))


def test_button() -> None:
    from ai.client import test_connection

    ok, message = test_connection(controller.config.data["ai"])
    note(f"test_connection -> {ok} | {message}")


def final_shot() -> None:
    note(f"final deltas={state['deltas']} text={state['text']!r} error={state['error']!r}")
    note(f"history={controller._history}")
    app.primaryScreen().grabWindow(0).save(str(OUT / "v9_ai_done.png"))


def finish() -> None:
    controller.config.data["ai"] = original_ai            # never keep the test endpoint
    controller._history = original_history
    note("restored original ai settings; quitting")
    controller.config.save()
    controller.quit()


QTimer.singleShot(600, send)
QTimer.singleShot(2000, mid_shot)
QTimer.singleShot(6000, test_button)
QTimer.singleShot(9000, final_shot)
QTimer.singleShot(9500, finish)
note("entering exec")
app.exec()
if server is not None:
    server.shutdown()
note("done")