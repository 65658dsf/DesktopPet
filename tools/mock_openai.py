"""Minimal OpenAI-compatible mock server (SSE streaming) for offline testing."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPLY = "累就停手，我说过几遍了。屏幕这边我看着，你只管去休息。"


def _chunks(text: str):
    for index in range(0, len(text), 3):
        yield text[index:index + 3]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:            # silence request logging
        pass

    def do_POST(self) -> None:                        # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {}
        if not self.path.endswith("/chat/completions"):
            self.send_error(404, "not found")
            return
        stream = bool(body.get("stream"))
        model = body.get("model", "mock-model")
        if not stream:
            payload = {
                "id": "mock", "object": "chat.completion", "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": REPLY},
                             "finish_reason": "stop"}],
            }
            data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def write_line(text: str) -> None:
            blob = text.encode("utf-8")
            self.wfile.write(f"{len(blob):X}\r\n".encode())
            self.wfile.write(blob + b"\r\n")
            self.wfile.flush()

        for piece in _chunks(REPLY):
            chunk = {
                "id": "mock", "object": "chat.completion.chunk", "model": model,
                "choices": [{"index": 0, "delta": {"content": piece}}],
            }
            write_line(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")
            time.sleep(0.09)
        write_line("data: [DONE]\n\n")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()


def start(port: int = 8765) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    start()
    print("mock OpenAI server on http://127.0.0.1:8765/v1")
    while True:
        time.sleep(1)