"""Stdlib HTTP server for the command library dashboard."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from sonoscribe.apps import app_icon_png, list_installed_apps, pick_result
from sonoscribe.catalog import (
    ConfirmRequired,
    LibraryError,
    apply_library_update,
    load_library,
    public_library,
    save_library,
)
from sonoscribe.lock import (
    LockController,
    LockError,
    cookie_value,
    lock_enabled,
    set_cookie_header,
    clear_cookie_header,
)
from sonoscribe.profile import username_error
from sonoscribe.settings import (
    add_custom_model,
    load_settings,
    lookup_model,
    public_account,
    public_model_state,
    public_settings,
    public_scout,
    remove_custom_model,
    update_settings,
)
from sonoscribe.scout import (
    KeychainError,
    cancel_scout,
    confirm_scout,
    current_scout,
    delete_scouts,
    rename_scout,
    request_insert,
    set_scout_continue,
    set_scout_key,
    scout_continue_id,
    scout_history,
)
from sonoscribe.stats import StatsStore
from sonoscribe.sync import (
    SyncError,
    confirm_key,
    disable,
    enable,
    import_key,
    join,
    pull,
    push,
    reveal_key,
    set_keychain_scope,
    sign_in,
    status,
    validate,
)
from sonoscribe.scribe.store import (
    create_from_text,
    delete_vocanotes,
    dismiss_vocanote,
    list_vocanotes,
    upsert_vocanote,
)
from sonoscribe.transcriber import TranscribeError

DEFAULT_PORT = 8741
VIEWS = frozenset({"overview", "commands", "routines", "voice", "scout", "scribe"})
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


def _push_in_background() -> None:
    settings = load_settings()
    sync = settings.get("sync") or {}
    if not sync.get("enabled") or sync.get("needs_confirm") or sync.get("needs_key") or sync.get("needs_create"):
        return

    def run() -> None:
        try:
            push()
        except SyncError:
            return

    threading.Thread(target=run, daemon=True).start()


def static_dir() -> Path:
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return meipass / "sonoscribe" / "dashboard" / "static"
    return Path(__file__).resolve().parent / "static"


_SYNC_CONFIRM = {
    "/api/sync/enable",
    "/api/sync/join",
    "/api/sync/validate",
    "/api/sync/confirm",
    "/api/sync/import-key",
    "/api/sync/reveal-key",
    "/api/sync/keychain-scope",
    "/api/sync/disable",
    "/api/sync/sign-in",
}


class DashboardServer:
    def __init__(
        self,
        stats: StatsStore,
        pick_path: Callable[[], str | None] | None = None,
        pick_app: Callable[[], dict[str, str] | None] | None = None,
        start_key_capture: Callable[[], dict[str, Any]] | None = None,
        stop_key_capture: Callable[[], dict[str, Any]] | None = None,
        drain_key_capture: Callable[[], dict[str, Any]] | None = None,
        set_model: Callable[[str], dict[str, Any]] | None = None,
        model_status: Callable[[], dict[str, Any]] | None = None,
        host: str = "127.0.0.1",
        port: int | None = None,
    ) -> None:
        self.stats = stats
        self.pick_path = pick_path
        self.pick_app = pick_app
        self.start_key_capture = start_key_capture
        self.stop_key_capture = stop_key_capture
        self.drain_key_capture = drain_key_capture
        self.set_model = set_model
        self.model_status = model_status
        self.lock = LockController()
        self.host = host
        self.port = port if port is not None else dashboard_port()
        self.url = f"http://{self.host}:{self.port}/"
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._test_lock = threading.Lock()
        self._test_listen = False
        self._test_text = ""
        self._scribe_text = ""
        self._test_sink = "test"
        self._focus_lock = threading.Lock()
        self._client_seen = 0.0
        self._focus_view = ""
        self._open_brief = ""
        self._open_note = ""
        self._active_tab = ""
        self._client_view = ""

    def note_client(self, tab: str = "", view: str = "", claim: bool = False) -> str:
        ident = str(tab or "").strip()[:80]
        name = str(view or "").strip()
        if name not in VIEWS:
            name = ""
        with self._focus_lock:
            self._client_seen = time.monotonic()
            if ident:
                if claim or not self._active_tab:
                    self._active_tab = ident
                if ident == self._active_tab:
                    if name:
                        self._client_view = name
                    return "ok"
                return "stale"
            if name:
                self._client_view = name
            return "ok"

    def scout_page_open(self) -> bool:
        with self._focus_lock:
            if not self._client_seen or (time.monotonic() - self._client_seen) >= 20:
                return False
            return self._client_view == "scout"

    def request_focus(self, view: str) -> None:
        name = str(view or "").strip()
        if name not in VIEWS:
            return
        with self._focus_lock:
            self._focus_view = name

    def request_open_brief(self, run_id: str) -> None:
        ident = str(run_id or "").strip()
        with self._focus_lock:
            self._open_brief = ident
            if ident:
                self._focus_view = "scout"

    def request_open_note(self, note_id: str) -> None:
        ident = str(note_id or "").strip()
        with self._focus_lock:
            self._open_note = ident
            if ident:
                self._focus_view = "scribe"

    def client_open(self) -> bool:
        with self._focus_lock:
            return bool(self._client_seen) and (time.monotonic() - self._client_seen) < 20

    def consume_focus(self, tab: str = "") -> str:
        ident = str(tab or "").strip()
        with self._focus_lock:
            if ident and self._active_tab and ident != self._active_tab:
                return ""
            view = self._focus_view
            self._focus_view = ""
            return view

    def peek_open_brief(self, tab: str = "") -> str:
        ident = str(tab or "").strip()
        with self._focus_lock:
            if ident and self._active_tab and ident != self._active_tab:
                return ""
            return self._open_brief

    def consume_open_brief(self, tab: str = "") -> str:
        ident = str(tab or "").strip()
        with self._focus_lock:
            if ident and self._active_tab and ident != self._active_tab:
                return ""
            brief = self._open_brief
            self._open_brief = ""
            return brief

    def peek_open_note(self, tab: str = "") -> str:
        ident = str(tab or "").strip()
        with self._focus_lock:
            if ident and self._active_tab and ident != self._active_tab:
                return ""
            return self._open_note

    def consume_open_note(self, tab: str = "") -> str:
        ident = str(tab or "").strip()
        with self._focus_lock:
            if ident and self._active_tab and ident != self._active_tab:
                return ""
            note = self._open_note
            self._open_note = ""
            return note

    def test_state(self, live: dict[str, Any] | None = None) -> dict[str, Any]:
        live = live if isinstance(live, dict) else {}
        with self._test_lock:
            text = self._scribe_text if self._test_sink == "scribe" else self._test_text
            listen = self._test_listen
            sink = self._test_sink
        return {
            "text": text,
            "listen": listen,
            "sink": sink,
            "model": str(live.get("active") or live.get("model") or ""),
            "status": str(live.get("status") or "ready"),
            "phase": str(live.get("phase") or ""),
        }

    def set_test(self, patch: dict[str, Any] | None, live: dict[str, Any] | None = None) -> dict[str, Any]:
        patch = patch if isinstance(patch, dict) else {}
        with self._test_lock:
            if "sink" in patch:
                sink = str(patch.get("sink") or "test").strip()
                self._test_sink = sink if sink in {"test", "scribe"} else "test"
            if "listen" in patch:
                self._test_listen = bool(patch["listen"])
            if patch.get("clear"):
                if self._test_sink == "scribe":
                    self._scribe_text = ""
                else:
                    self._test_text = ""
        return self.test_state(live)

    def append_test(self, text: str) -> bool:
        chunk = str(text or "").strip()
        if not chunk:
            return False
        with self._test_lock:
            if not self._test_listen:
                return False
            if self._test_sink == "scribe":
                if self._scribe_text and not self._scribe_text.endswith((" ", "\n")):
                    self._scribe_text += " "
                self._scribe_text += chunk
            else:
                if self._test_text and not self._test_text.endswith((" ", "\n")):
                    self._test_text += " "
                self._test_text += chunk
            return True

    def test_listening(self) -> bool:
        with self._test_lock:
            return self._test_listen

    def presence_payload(self, query: str = "") -> dict[str, Any]:
        tab, view, claim = _parse_tab(query)
        status = self.note_client(tab=tab, view=view, claim=claim)
        if status == "stale":
            return {"focus": "", "open_id": "", "open_note": "", "tab": "stale"}
        return {
            "focus": self.consume_focus(tab),
            "open_id": self.peek_open_brief(tab),
            "open_note": self.peek_open_note(tab),
            "tab": "ok",
        }

    def scribe_payload(self, query: str = "", *, secrets: bool = False) -> dict[str, Any]:
        tab, view, claim = _parse_tab(query)
        status = self.note_client(tab=tab, view=view, claim=claim)
        items = list_vocanotes(secrets=secrets)
        gone = [
            str(item.get("id") or "").strip()
            for item in (load_library().get("vocanote_gone") or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]
        if status == "stale":
            return {"items": items, "gone": gone, "open_id": "", "focus": "", "tab": "stale"}
        return {
            "items": items,
            "gone": gone,
            "open_id": self.consume_open_note(tab),
            "focus": self.consume_focus(tab),
            "tab": "ok",
        }

    def scout_payload(self, query: str = "") -> dict[str, Any]:
        tab, view, claim = _parse_tab(query)
        status = self.note_client(tab=tab, view=view, claim=claim)
        if status == "stale":
            return {
                "runs": scout_history(),
                "current": current_scout(),
                "continue_id": scout_continue_id(),
                "open_id": "",
                "focus": "",
                "tab": "stale",
            }
        return {
            "runs": scout_history(),
            "current": current_scout(),
            "continue_id": scout_continue_id(),
            "open_id": self.consume_open_brief(tab),
            "focus": self.consume_focus(tab),
            "tab": "ok",
        }

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


def _parse_tab(query: str) -> tuple[str, str, bool]:
    qs = parse_qs(query or "", keep_blank_values=True)
    tab = str((qs.get("tab") or [""])[0] or "").strip()
    view = str((qs.get("view") or [""])[0] or "").strip()
    claim = str((qs.get("claim") or [""])[0] or "").strip().lower() in {"1", "true", "yes"}
    return tab, view, claim


def _make_handler(server: DashboardServer) -> type[BaseHTTPRequestHandler]:
    root = static_dir()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _lock_token(self) -> str | None:
            return cookie_value(self.headers.get("Cookie"))

        def _send_lock_error(self, exc: LockError | ConfirmRequired) -> None:
            if isinstance(exc, ConfirmRequired):
                self._send_json(401, {"error": str(exc) or "Confirm required.", "code": "confirm"})
                return
            self._send_json(exc.status, {"error": exc.message, "code": exc.code})

        def _allow_api(self, method: str, path: str) -> bool:
            if path.startswith("/api/lock"):
                return True
            if not lock_enabled():
                return True
            try:
                server.lock.require_unlocked(self._lock_token())
            except LockError as exc:
                self._send_lock_error(exc)
                return False
            return True

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/api/") and not self._allow_api("GET", path):
                return
            if path == "/api/lock/status":
                self._send_json(200, server.lock.status(self._lock_token()))
                return
            if path == "/api/library":
                library = load_library()
                if not server.lock.secrets_open(self._lock_token()):
                    library = public_library(library)
                self._send_json(200, library)
                return
            if path == "/api/stats":
                device = (parse_qs(parsed.query).get("device") or [None])[0]
                self._send_json(200, server.stats.snapshot(device))
                return
            if path == "/api/apps":
                self._send_json(200, {"apps": list_installed_apps()})
                return
            if path == "/api/apps/icon":
                bundle_id = (parse_qs(parsed.query).get("id") or [""])[0].strip()
                png = app_icon_png(bundle_id) if bundle_id else None
                if not png:
                    self.send_error(404, "Not found")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(png)
                return
            if path == "/api/settings":
                self._send_json(200, public_settings())
                return
            if path == "/api/model":
                live = server.model_status() if server.model_status else None
                self._send_json(200, public_model_state(live))
                return
            if path == "/api/model/test":
                live = server.model_status() if server.model_status else None
                self._send_json(200, server.test_state(live))
                return
            if path == "/api/presence":
                self._send_json(200, server.presence_payload(parsed.query))
                return
            if path == "/api/scout":
                self._send_json(200, server.scout_payload(parsed.query))
                return
            if path == "/api/scribe":
                secrets = server.lock.secrets_open(self._lock_token())
                self._send_json(200, server.scribe_payload(parsed.query, secrets=secrets))
                return
            if path == "/api/scout/current":
                self._send_json(200, {"current": current_scout()})
                return
            if path == "/api/scout/settings":
                self._send_json(200, public_scout())
                return
            if path == "/api/account":
                self._send_json(200, public_account())
                return
            if path == "/api/sync/status":
                self._send_json(200, status())
                return
            if path == "/api/keys/record/events":
                drain = server.drain_key_capture
                if drain is None:
                    self._send_json(200, {"keys": [], "stopped": False, "native": False})
                    return
                self._send_json(200, drain())
                return
            if path == "/":
                path = "/index.html"
            self._send_static(root, path)

        def do_PUT(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/api/") and not self._allow_api("PUT", path):
                return
            if path == "/api/lock":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    timeout = int(payload.get("timeout_sec"))
                    data = server.lock.set_timeout(timeout, self._lock_token())
                except (TypeError, ValueError):
                    self._send_json(400, {"error": "Invalid auto-lock time."})
                    return
                except LockError as exc:
                    self._send_lock_error(exc)
                    return
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                self._send_json(200, data)
                return
            if parsed.path == "/api/account":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    patch: dict[str, Any] = {}
                    if "username" in payload:
                        text = str(payload.get("username") or "").strip()
                        error = username_error(text) if text else None
                        if error:
                            self._send_json(400, {"error": error})
                            return
                        current_name = str(load_settings().get("username") or "")
                        if text != current_name:
                            try:
                                server.lock.require_confirm(self._lock_token())
                            except LockError as exc:
                                self._send_lock_error(exc)
                                return
                        patch["username"] = text
                    if isinstance(payload.get("device"), dict):
                        patch["device"] = {"name": payload["device"].get("name")}
                    if "private_mode" in payload:
                        patch["private_mode"] = bool(payload["private_mode"])
                    saved = update_settings(patch) if patch else load_settings()
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                self._send_json(200, public_account(saved))
                _push_in_background()
                return
            if parsed.path == "/api/model":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    key = str(payload.get("model") or "").strip()
                    if lookup_model(key) is None:
                        self._send_json(400, {"error": "Unknown model."})
                        return
                    if server.set_model is not None:
                        live = server.set_model(key)
                    else:
                        update_settings({"model": key})
                        live = None
                except TranscribeError as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                self._send_json(200, public_model_state(live))
                return
            if parsed.path == "/api/scout/settings":
                try:
                    if not lock_enabled():
                        self._send_json(400, {"error": "set a lock first"})
                        return
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    saved = update_settings({"scout": payload})
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                self._send_json(200, public_scout(saved))
                return
            if parsed.path == "/api/settings":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    previous = load_settings()
                    if "scout" in payload or "tasks" in payload:
                        payload = dict(payload)
                        payload.pop("scout", None)
                        payload.pop("tasks", None)
                    if "lock" in payload and isinstance(payload.get("lock"), dict):
                        payload = dict(payload)
                        timeout = payload["lock"].get("timeout_sec")
                        payload["lock"] = {"timeout_sec": timeout} if timeout is not None else {}
                        if not payload["lock"]:
                            payload.pop("lock")
                    if payload.get("keychain_scope") and payload.get("keychain_scope") != previous.get("keychain_scope"):
                        try:
                            server.lock.require_confirm(self._lock_token())
                        except LockError as exc:
                            self._send_lock_error(exc)
                            return
                    if "username" in payload and str(payload.get("username") or "").strip() != str(previous.get("username") or ""):
                        try:
                            server.lock.require_confirm(self._lock_token())
                        except LockError as exc:
                            self._send_lock_error(exc)
                            return
                    saved = update_settings(payload)
                    if saved["keychain_scope"] != previous.get("keychain_scope"):
                        set_keychain_scope(saved["keychain_scope"])
                    if saved["model"] != previous.get("model") and server.set_model is not None:
                        server.set_model(saved["model"])
                except SyncError as exc:
                    self._send_json(400, {"error": exc.message, "details": exc.details})
                    return
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                self._send_json(200, public_settings(saved))
                _push_in_background()
                return
            if parsed.path != "/api/library":
                self._send_json(404, {"error": "Not found"})
                return
            try:
                payload = self._read_json()
                token = self._lock_token()
                status = server.lock.status(token)
                saved = save_library(
                    apply_library_update(
                        load_library(),
                        payload,
                        revealed=server.lock.secrets_open(token),
                        confirmed=(not status["enabled"]) or status["confirmed"],
                        lock_on=bool(status["enabled"]),
                    )
                )
                if not server.lock.secrets_open(token):
                    saved = public_library(saved)
            except ConfirmRequired as exc:
                self._send_lock_error(exc)
                return
            except LibraryError as exc:
                self._send_json(400, {"error": str(exc), "errors": exc.errors})
                return
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON"})
                return
            self._send_json(200, saved)
            _push_in_background()

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/api/") and not self._allow_api("POST", path):
                return
            if path.startswith("/api/lock"):
                self._handle_lock_post(path)
                return
            if path == "/api/scout/confirm":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                self._send_json(200, {"current": confirm_scout(bool(payload.get("ok")))})
                return
            if path == "/api/scout/insert":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    run = request_insert(str(payload.get("id") or ""))
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                if run is None:
                    self._send_json(400, {"error": "Nothing to insert."})
                    return
                self._send_json(200, {"run": run})
                return
            if path == "/api/scout/cancel":
                self._send_json(200, {"current": cancel_scout()})
                return
            if path == "/api/scout/continue":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    wanted = str(payload.get("id") or "")
                    cont = set_scout_continue(wanted)
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                if wanted.strip() and not cont:
                    self._send_json(400, {"error": "Could not continue that brief."})
                    return
                self._send_json(200, {"continue_id": cont, "current": current_scout(), "runs": scout_history()})
                return
            if path == "/api/scout/delete":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    ids = payload.get("ids") or []
                    if not isinstance(ids, list):
                        self._send_json(400, {"error": "ids required"})
                        return
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                self._send_json(200, delete_scouts([str(item) for item in ids]))
                return
            if path == "/api/scout/title":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    run = rename_scout(str(payload.get("id") or ""), str(payload.get("title") or ""))
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                if run is None:
                    self._send_json(400, {"error": "Could not rename that brief."})
                    return
                self._send_json(200, {"run": run})
                return
            if path == "/api/scout/key":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    if not lock_enabled():
                        self._send_json(400, {"error": "set a lock first"})
                        return
                    try:
                        server.lock.require_confirm(self._lock_token())
                    except LockError as exc:
                        self._send_lock_error(exc)
                        return
                    provider = str(
                        payload.get("provider")
                        or (load_settings().get("scout") or {}).get("provider")
                        or ""
                    )
                    set_scout_key(provider, str(payload.get("key") or ""))
                except KeychainError as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                self._send_json(200, public_scout())
                return
            if path == "/api/scribe":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    text = str(payload.get("text") or "").strip()
                    if (
                        text
                        and not payload.get("id")
                        and not payload.get("due_at")
                        and "is_todo" not in payload
                        and "is_reminder" not in payload
                    ):
                        note = create_from_text(text)
                    else:
                        note = upsert_vocanote(payload, parse_text=text or None)
                except LibraryError as exc:
                    self._send_json(400, {"error": str(exc), "errors": exc.errors})
                    return
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                secrets = server.lock.secrets_open(self._lock_token())
                self._send_json(200, {"item": note, "items": list_vocanotes(secrets=secrets)})
                _push_in_background()
                return
            if path == "/api/model/test":
                try:
                    payload = self._read_json()
                    if payload is not None and not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                live = server.model_status() if server.model_status else None
                self._send_json(200, server.set_test(payload, live))
                return
            if path == "/api/model/custom":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    saved = add_custom_model(
                        str(payload.get("path") or ""),
                        str(payload.get("name") or ""),
                    )
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                key = saved["model"]
                live = server.set_model(key) if server.set_model is not None else None
                self._send_json(200, public_model_state(live))
                return
            if path == "/api/model/custom/remove":
                try:
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"error": "Invalid JSON"})
                        return
                    saved = remove_custom_model(str(payload.get("id") or ""))
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                live = None
                if server.set_model is not None:
                    live = server.set_model(saved["model"])
                self._send_json(200, public_model_state(live))
                return
            if path == "/api/pick-path":
                picker = server.pick_path
                if picker is None:
                    self._send_json(501, {"error": "Path picker is unavailable"})
                    return
                chosen = picker()
                self._send_json(200, {"path": chosen})
                return
            if path == "/api/pick-app":
                picker = server.pick_app
                if picker is None:
                    self._send_json(501, {"error": "App picker is unavailable"})
                    return
                chosen = pick_result(picker())
                self._send_json(200, chosen or {"name": "", "bundle_id": "", "path": None})
                return
            if path == "/api/keys/record/start":
                starter = server.start_key_capture
                if starter is None:
                    self._send_json(200, {"ok": False, "native": False})
                    return
                self._send_json(200, starter())
                return
            if path == "/api/keys/record/stop":
                stopper = server.stop_key_capture
                if stopper is None:
                    self._send_json(200, {"ok": True, "native": False, "keys": [], "stopped": False})
                    return
                self._send_json(200, stopper())
                return
            handlers = {
                "/api/sync/enable": lambda body: enable(body if isinstance(body, dict) else {}),
                "/api/sync/join": lambda body: join(body if isinstance(body, dict) else {}),
                "/api/sync/validate": lambda body: validate(body if isinstance(body, dict) else {}),
                "/api/sync/confirm": lambda body: confirm_key(str((body or {}).get("pem") or "") or None),
                "/api/sync/import-key": lambda body: import_key(str((body or {}).get("pem") or "")),
                "/api/sync/reveal-key": lambda _body: reveal_key(),
                "/api/sync/keychain-scope": lambda body: set_keychain_scope(
                    str((body or {}).get("keychain_scope") or "")
                ),
                "/api/sync/disable": lambda _body: disable(),
                "/api/sync/sign-in": lambda body: sign_in(body if isinstance(body, dict) else {}),
                "/api/sync/push": lambda _body: push(),
                "/api/sync/pull": lambda _body: pull(),
            }
            handler = handlers.get(path)
            if handler is None:
                self._send_json(404, {"error": "Not found"})
                return
            try:
                body = self._read_json()
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON"})
                return
            if path in _SYNC_CONFIRM:
                try:
                    server.lock.require_confirm(self._lock_token())
                except LockError as exc:
                    self._send_lock_error(exc)
                    return
            try:
                self._send_json(200, handler(body if isinstance(body, dict) else {}))
            except SyncError as exc:
                self._send_json(400, {"error": exc.message, "details": exc.details, "kind": exc.kind})

        def do_PATCH(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/api/") and not self._allow_api("PATCH", path):
                return
            if path != "/api/scribe":
                self._send_json(404, {"error": "Not found"})
                return
            try:
                payload = self._read_json()
                if not isinstance(payload, dict):
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                ident = str(payload.get("id") or "").strip()
                if payload.get("dismiss"):
                    note = dismiss_vocanote(ident)
                    if note is None:
                        self._send_json(404, {"error": "Not found"})
                        return
                else:
                    note = upsert_vocanote(payload)
            except LibraryError as exc:
                self._send_json(400, {"error": str(exc), "errors": exc.errors})
                return
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON"})
                return
            secrets = server.lock.secrets_open(self._lock_token())
            self._send_json(200, {"item": note, "items": list_vocanotes(secrets=secrets)})
            _push_in_background()

        def do_DELETE(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/api/") and not self._allow_api("DELETE", path):
                return
            if path != "/api/scribe":
                self._send_json(404, {"error": "Not found"})
                return
            try:
                payload = self._read_json()
                if not isinstance(payload, dict):
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                raw_ids = payload.get("ids")
                if not isinstance(raw_ids, list):
                    raw_ids = [payload.get("id")]
                ids = [str(item).strip() for item in raw_ids if str(item or "").strip()]
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON"})
                return
            result = delete_vocanotes(ids)
            if not server.lock.secrets_open(self._lock_token()):
                result = {"ok": True, "items": list_vocanotes(secrets=False)}
            self._send_json(200, result)
            _push_in_background()

        def _handle_lock_post(self, path: str) -> None:
            token = self._lock_token()
            try:
                payload = self._read_json()
                if payload is not None and not isinstance(payload, dict):
                    self._send_json(400, {"error": "Invalid JSON"})
                    return
                body = payload if isinstance(payload, dict) else {}
                if path == "/api/lock/setup":
                    data, cookie = server.lock.setup(body, token)
                    self._send_json(200, {**data, "token": cookie}, cookies=[set_cookie_header(cookie)])
                    return
                if path == "/api/lock/disable":
                    data = server.lock.disable(token, str(body.get("pin") or ""))
                    self._send_json(200, data, cookies=[clear_cookie_header()])
                    return
                if path == "/api/lock/unlock":
                    data, cookie = server.lock.unlock_pin(str(body.get("pin") or ""))
                    self._send_json(200, {**data, "token": cookie}, cookies=[set_cookie_header(cookie)])
                    return
                if path == "/api/lock/lock":
                    data = server.lock.lock_now(token)
                    self._send_json(200, data, cookies=[clear_cookie_header()])
                    return
                if path == "/api/lock/activity":
                    self._send_json(200, server.lock.activity(token))
                    return
                if path == "/api/lock/confirm":
                    self._send_json(200, server.lock.confirm_pin(str(body.get("pin") or ""), token))
                    return
                if path == "/api/lock/secrets":
                    self._send_json(200, server.lock.set_secrets(bool(body.get("reveal")), token))
                    return
            except LockError as exc:
                self._send_lock_error(exc)
                return
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON"})
                return
            self._send_json(404, {"error": "Not found"})

        def _read_json(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8"))

        def _send_json(self, status: int, payload: Any, cookies: list[str] | None = None) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for cookie in cookies or []:
                self.send_header("Set-Cookie", cookie)
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
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return Handler
