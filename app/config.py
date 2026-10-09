"""Settings persistence.

Follows the Desktop Pet Launcher contract (`settings.json`) and store paths:
  %APPDATA%\\top.nether.pet\\settings.json
plus our own `ai` / `behavior extras` sections. Portable mode: if `portable.txt`
sits next to the program, settings are stored beside it instead.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "top.nether.pet"

DEFAULT_SYSTEM_PROMPT = """你是《恋与深空》里的秦彻（Sylus），N109区的掌控者。
外貌：银白色短发、红色眼瞳，黑红配色的中式装束，肩上有深色车线软甲外套。
性格：慵懒从容、危险而强势，带着戏谑与掌控感；说话直接、简短、有分量，偶尔流露温柔的占有欲；喜欢逗弄对方，从不废话。

现在你以 Q 版形象作为用户的桌面宠物待在屏幕上：
- 用中文回复，口语化，控制在 1~3 句，像真的在屏幕里跟人说话。
- 保持角色语气，不要出戏，不要提及自己是 AI、模型或程序。
- 用户互动时（打招呼、闲聊、抱怨、撒娇、求助）自然回应，可以带一点调侃与掌控感。
- 如果用户请你做事（提醒、陪你、叫你休息），可以答应得理所当然。
"""

DEFAULTS: dict = {
    # --- Desktop Pet Launcher contract keys -------------------------------
    "activePetId": "qinche-q",
    "width": 192,
    "height": 208,
    "x": None,
    "y": None,
    "alwaysOnTop": True,
    "dragEnabled": True,
    "locked": False,
    "clickThrough": False,
    "reducedMotion": False,
    "animationSpeed": 1.0,
    "manualState": "auto",
    "manualStateVersion": 1,
    "autostart": False,
    "showOnStartup": True,
    "pixelated": False,
    "idleVariety": True,
    "keepAspectRatio": True,
    "petFolders": [],
    # --- extension: AI ----------------------------------------------------
    "ai": {
        "mode": "local",                 # "local" = 完全离线 | "online" = OpenAI 兼容接口
        "baseUrl": "https://api.openai.com/v1",
        "apiKey": "",
        "model": "gpt-4o-mini",
        "temperature": 0.8,
        "maxTokens": 512,
        "systemPrompt": DEFAULT_SYSTEM_PROMPT,
        "historyLimit": 100,
        "stream": True,
    },
    # --- extension: pet behaviour ----------------------------------------
    "chat": {"fontSize": 14, "bubbleSeconds": 6},
}


def data_dir() -> Path:
    """Resolve the folder used for settings, chat history and caches."""
    exe_dir = Path(sys.argv[0]).resolve().parent
    if (exe_dir / "portable.txt").exists():
        return exe_dir
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    def __init__(self) -> None:
        self.path = data_dir() / "settings.json"
        self.data: dict = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        self.data = dict(DEFAULTS)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                # Before the explicit auto/idle choice, "idle" meant automatic
                # quiet actions. Migrate that old meaning once; a versioned
                # idle selection now means only the idle/blinking animation.
                if "manualStateVersion" not in raw:
                    if raw.get("manualState") == "idle":
                        raw["manualState"] = "auto"
                    raw["manualStateVersion"] = 1
                self.data = _merge(DEFAULTS, raw)
        except FileNotFoundError:
            pass
        except (json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError:
            pass

    # convenience accessors -------------------------------------------------
    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value
        self.save()

    @property
    def ai(self) -> dict:
        return self.data["ai"]

    def set_ai(self, key: str, value) -> None:
        self.data["ai"][key] = value
        self.save()
