from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from memory_store import NeuroSeedMemoryStore


HOST = "127.0.0.1"
PORT = 8077
STORE = NeuroSeedMemoryStore()


class NeuroSeedHandler(BaseHTTPRequestHandler):
    server_version = "NeuroSeedMemory/1.0"

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json({
                "status": "ok",
                "project": "07-NeuroSeed",
                "storage": "sqlite",
                "chroma": STORE._chroma_collection() is not None,
            })
            return
        if path == "/neuroseed/state":
            self._send_json({"state": STORE.get_state()})
            return
        self._send_json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/neuroseed/state":
            self._send_json({"error": "not_found"}, status=404)
            return
        try:
            payload = self._read_json()
            state = STORE.upsert_state(payload)
            self._send_json({"state": state})
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid_json"}, status=400)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path == "/neuroseed/state":
            self._send_json({"state": STORE.reset()})
            return
        self._send_json({"error": "not_found"}, status=404)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), NeuroSeedHandler)
    print(f"NeuroSeed memory server running at http://{HOST}:{PORT}")
    print("Open prototype/index.html to use the UI. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
