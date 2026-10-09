"""OpenAI-compatible chat client with streaming (runs off the GUI thread).

Works with any `/chat/completions` style endpoint: OpenAI, DeepSeek, Moonshot,
SiliconFlow, and local servers such as Ollama (`http://localhost:11434/v1`) or
LM Studio / vLLM — so the program can stay fully offline with a local model.
"""

from __future__ import annotations

import json
import threading

import requests
from PySide6.QtCore import QObject, Signal

REQUEST_TIMEOUT = (10, 180)


def normalize_url(base_url: str) -> str:
    url = (base_url or "").strip().rstrip("/")
    if not url:
        raise ValueError("接口地址为空")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1") or url.endswith("/v1beta") or "/v1/" in url:
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


def _decode_body(response) -> str:
    """Decode a body as UTF-8 first — endpoints often omit the charset, which
    would otherwise make requests fall back to ISO-8859-1 and garble Chinese."""
    data = response.content or b""
    for encoding in ("utf-8", response.encoding or "utf-8"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


class ChatEngine(QObject):
    """Emits streamed deltas from a background thread."""

    delta = Signal(str)
    done = Signal(str)
    error = Signal(str)
    started = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def cancel(self) -> None:
        self._cancel.set()

    def send(self, messages: list[dict], cfg: dict) -> None:
        if self.busy:
            return
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(messages, dict(cfg)), daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ #
    def _run(self, messages: list[dict], cfg: dict) -> None:
        self.started.emit()
        try:
            url = normalize_url(cfg.get("baseUrl", ""))
            headers = {"Content-Type": "application/json"}
            if cfg.get("apiKey"):
                headers["Authorization"] = f"Bearer {cfg['apiKey']}"
            stream = bool(cfg.get("stream", True))
            payload = {
                "model": cfg.get("model", "gpt-4o-mini"),
                "messages": messages,
                "temperature": float(cfg.get("temperature", 0.8)),
                "max_tokens": int(cfg.get("maxTokens", 512)),
                "stream": stream,
            }
            with requests.post(url, headers=headers, json=payload, stream=stream,
                               timeout=REQUEST_TIMEOUT) as response:
                if response.status_code >= 400:
                    body = _decode_body(response)[:300].replace("\n", " ")
                    raise RuntimeError(f"HTTP {response.status_code} — {body}")
                text = self._read_stream(response) if stream else self._read_once(response)
            self.done.emit(text)
        except Exception as exc:                                  # noqa: BLE001
            self.error.emit(f"{type(exc).__name__}: {exc}")

    def _read_stream(self, response) -> str:
        """Parse an SSE stream.

        Bytes are decoded as UTF-8 explicitly: many OpenAI-compatible endpoints
        (and most self-hosted ones) send `text/event-stream` without a charset,
        which makes `requests` fall back to ISO-8859-1 and turns every non-ASCII
        character into mojibake.
        """
        pieces: list[str] = []
        for raw in response.iter_lines(decode_unicode=False):
            if self._cancel.is_set():
                break
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line:
                continue
            if line == "[DONE]":
                break
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            piece = (choice.get("delta") or {}).get("content") or ""
            if not piece:
                piece = (choice.get("message") or {}).get("content") or ""
            if piece:
                pieces.append(piece)
                self.delta.emit(piece)
        return "".join(pieces)

    @staticmethod
    def _read_once(response) -> str:
        obj = json.loads(_decode_body(response))
        choices = obj.get("choices") or []
        if not choices:
            raise RuntimeError(f"接口返回内容异常: {str(obj)[:200]}")
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")


def test_connection(cfg: dict) -> tuple[bool, str]:
    """Blocking connectivity probe for the settings panel."""
    try:
        url = normalize_url(cfg.get("baseUrl", ""))
        headers = {"Content-Type": "application/json"}
        if cfg.get("apiKey"):
            headers["Authorization"] = f"Bearer {cfg['apiKey']}"
        payload = {
            "model": cfg.get("model", "gpt-4o-mini"),
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 8,
            "stream": False,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=(8, 30))
        if response.status_code >= 400:
            return False, f"HTTP {response.status_code} — {_decode_body(response)[:200]}"
        obj = json.loads(_decode_body(response))
        model = obj.get("model") or cfg.get("model")
        return True, f"连接成功（model: {model}）"
    except Exception as exc:                                      # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"