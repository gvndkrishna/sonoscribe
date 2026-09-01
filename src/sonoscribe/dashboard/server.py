"""Stdlib HTTP server for the command library dashboard."""

from __future__ import annotations

import json
import os
import sys
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sonoscribe.catalog import LibraryError, load_library, save_library, validate_library
from sonoscribe.stats import StatsStore

DEFAULT_PORT = 8741
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
}


def dashboard_port() -> int:
    raw = os.environ.get("SONOSCRIBE_DASHBOARD_PORT")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_PORT


def static_dir() -> Path:
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return meipass / "sonoscribe" / "dashboard" / "static"
    return Path(__file__).resolve().parent / "static"


class DashboardServer:
    def __init__(
        self,
        stats: StatsStore,
        pick_path: Callable[[], str | None] | None = None,
        host: str = "127.0.0.1",
        port: int | None = None,
    ) -> None:
        self.stats = stats
        self.pick_path = pick_path
        self.host = host
        self.port = port if port is not None else dashboard_port()
        self.url = f"http://{self.host}:{self.port}/"
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        handler = _make_handler(self)
        httpd = ThreadingHTTPServer((self.host, self.port), handler)
        httpd.daemon_threads = True
        self.port = int(httpd.server_address[1])
        self.url = f"http://{self.host}:{self.port}/"
        self._httpd = httpd
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self._thread = thread

    def stop(self) -> None:
        httpd = self._httpd
        self._httpd = None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()


def _make_handler(server: DashboardServer) -> type[BaseHTTPRequestHandler]:
    root = static_dir()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/library":
                self._send_json(200, load_library())
                return
            if path == "/api/stats":
                self._send_json(200, server.stats.snapshot())
                return
            if path == "/":
                path = "/index.html"
            self._send_static(root, path)

        def do_PUT(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/library":
                self._send_json(404, {"error": "Not found"})
                return
            try:
                payload = self._read_json()
                saved = save_library(validate_library(payload))
            except LibraryError as exc:
                self._send_json(400, {"error": str(exc), "errors": exc.errors})
                return
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON"})
                return
            self._send_json(200, saved)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/pick-path":
                self._send_json(404, {"error": "Not found"})
                return
            picker = server.pick_path
            if picker is None:
                self._send_json(501, {"error": "Path picker is unavailable"})
                return
            chosen = picker()
            self._send_json(200, {"path": chosen})

        def _read_json(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8"))

        def _send_json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_static(self, base: Path, url_path: str) -> None:
            relative = url_path.lstrip("/")
            if not relative or ".." in Path(relative).parts:
                self._send_json(404, {"error": "Not found"})
                return
            target = (base / relative).resolve()
            try:
                target.relative_to(base.resolve())
            except ValueError:
                self._send_json(404, {"error": "Not found"})
                return
            if not target.is_file():
                self.send_error(404, "Not found")
                return
            data = target.read_bytes()
            mime = _MIME.get(target.suffix.lower(), "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler
