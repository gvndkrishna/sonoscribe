"""Hold Fn → record → Whisper → clean → paste. Fn+Cmd → commands."""

from __future__ import annotations

import queue
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSModalResponseOK,
    NSOpenPanel,
)
from Foundation import NSObject, NSOperationQueue, NSThread, NSURL
import numpy as np
import objc

from sonoscribe.apps import frontmost_app, read_app
from sonoscribe.catalog import (
    command_by_id,
    load_library,
    match_utterance,
    skip_stats,
    usable_library,
)
from sonoscribe.cleaner import prepare_command_text, process
from sonoscribe.dashboard.server import DashboardServer
from sonoscribe.executor import KeyboardState, run_command, run_routine_steps
from sonoscribe.fn_monitor import FnMonitor, FnMonitorError
from sonoscribe.inserter import insert
from sonoscribe.key_capture import KeyCapture
from sonoscribe.slots import variable_map
from sonoscribe.permissions import (
    accessibility_granted,
    open_accessibility_settings,
    permission_help,
    prompt_accessibility,
)
from sonoscribe.recorder import (
    MINIMUM_SAMPLES,
    SAMPLE_RATE,
    Recorder,
    RecorderError,
    attach_preroll,
    take_command_preroll,
)
from sonoscribe.stats import StatsStore
from sonoscribe.notify import (
    BUBBLE_SECONDS,
    notice_body,
    notice_cancel_label,
    notice_dismiss_label,
    notice_insert_label,
    notice_kicker,
    notice_later_label,
    notice_menu_label,
    notice_run_label,
    notice_script_body,
    reminder_done_label,
    reminder_kicker,
    reminder_title,
)
from sonoscribe.scout import (
    ScoutBusy,
    ScoutConfigError,
    confirm_scout,
    set_brief_insert,
    set_brief_notice,
    set_scout_continue,
    spoken_confirm,
    start_scout,
)
from sonoscribe.transcriber import DEFAULT_MODEL, TranscribeError, Transcriber, friendly_load_error

MIN_HOLD_SECONDS = 0.25


def _model_spec(key: str) -> dict[str, Any] | None:
    from sonoscribe.settings import lookup_model

    return lookup_model(key)


def _log(message: str) -> None:
    print(message, flush=True)


def _safe_frontmost() -> dict[str, str] | None:
    try:
        return frontmost_app()
    except Exception:
        return None


def _on_main(fn) -> None:
    if NSThread.isMainThread():
        fn()
        return
    NSOperationQueue.mainQueue().addOperationWithBlock_(fn)


@dataclass(frozen=True)
class _Job:
    kind: str
    samples: np.ndarray
    session: int
    frontmost: dict[str, str] | None = None


class _StatusMenuTarget(NSObject):
    """Cocoa target for the menu extra. A Python function is not a valid ObjC selector."""

    _owner = objc.ivar()

    def dashboard_(self, _sender=None):
        owner = self._owner
        if owner is not None:
            owner._open_dashboard(force=True)

    def openBrief_(self, sender=None):
        owner = self._owner
        if owner is None:
            return
        run_id = ""
        if sender is not None:
            try:
                run_id = str(sender.representedObject() or "")
            except Exception:
                run_id = ""
        owner._open_pending_brief(run_id)

    def insertBrief_(self, sender=None):
        owner = self._owner
        if owner is None:
            return
        run_id = ""
        if sender is not None:
            try:
                run_id = str(sender.representedObject() or "")
            except Exception:
                run_id = ""
        owner._insert_pending_brief(run_id)

    def confirmBrief_(self, _sender=None):
        owner = self._owner
        if owner is not None:
            owner._confirm_pending_brief(True)

    def cancelBrief_(self, _sender=None):
        owner = self._owner
        if owner is not None:
            owner._confirm_pending_brief(False)

    def closeBriefBubble_(self, _sender=None):
        owner = self._owner
        if owner is not None:
            owner._dismiss_brief_bubble()

    def openScribeNote_(self, sender=None):
        owner = self._owner
        if owner is None:
            return
        note_id = ""
        if sender is not None:
            try:
                note_id = str(sender.representedObject() or "")
            except Exception:
                note_id = ""
        owner._open_pending_note(note_id)

    def doneScribeNote_(self, sender=None):
        owner = self._owner
        if owner is None:
            return
        note_id = ""
        if sender is not None:
            try:
                note_id = str(sender.representedObject() or "")
            except Exception:
                note_id = ""
        owner._done_pending_note(note_id)

    def closeScribeBubble_(self, _sender=None):
        owner = self._owner
        if owner is not None:
            owner._dismiss_scribe_bubble(advance=True)

    def quit_(self, _sender=None):
        owner = self._owner
        if owner is not None:
            owner._quit()


class _BriefPopoverDelegate(NSObject):
    _owner = objc.ivar()

    def popoverDidClose_(self, _notification=None):
        owner = self._owner
        if owner is not None:
            owner._dismiss_brief_bubble()


class App:
    def __init__(self, model: str, remove_fillers: bool, copy_only: bool) -> None:
        self.remove_fillers = remove_fillers
        self.copy_only = copy_only
        self.recorder = Recorder()
        spec = _model_spec(model) or _model_spec(DEFAULT_MODEL) or {
            "id": DEFAULT_MODEL,
            "label": DEFAULT_MODEL,
            "path": None,
        }
        self.transcriber = Transcriber(spec["id"], spec.get("path"))
        self.stats = StatsStore()
        self.keyboard = KeyboardState()
        self._lock = threading.Lock()
        self._phase = "idle"
        self._hold_started: float | None = None
        self._slice_start = 0
        self._in_command = False
        self._used_command = False
        self._command_frontmost: dict[str, str] | None = None
        self._command_preroll = np.zeros(0, dtype=np.float32)
        self._session = 0
        self._pending = 0
        self._want_idle = False
        self._jobs: queue.Queue[_Job] = queue.Queue()
        self._monitor = FnMonitor(
            self.on_begin,
            self.on_end,
            self.on_cancel,
            self.on_command_begin,
            self.on_command_end,
        )
        self._status_item = None
        self._status_menu = None
        self._status_target = None
        self._dashboard_item = None
        self._brief_menu_item = None
        self._brief_menu_sep = None
        self._brief_popover = None
        self._brief_popover_delegate = None
        self._brief_insert_btn = None
        self._brief_close_btn = None
        self._brief_action_btns = []
        self._pending_brief_id = ""
        self._pending_open_url = ""
        self._pending_note_id = ""
        self._notice_kind = ""
        self._scribe_done_btn = None
        self._bubble_token = 0
        self._dashboard: DashboardServer | None = None
        self._key_capture = KeyCapture()
        self._quitting = False
        self._wanted_model = spec["id"]
        self._model_status = "loading"
        self._model_error = ""
        self._model_lock = threading.Lock()
        threading.Thread(target=self._job_loop, daemon=True).start()

    def run(self) -> int:
        if not accessibility_granted():
            _log(permission_help())
            _log("Prompting Accessibility now…")
            prompt_accessibility()
            open_accessibility_settings()
            if not accessibility_granted():
                _log("Accessibility is still off. Grant it, then run sonoscribe again.")
                return 1

        nsapp = NSApplication.sharedApplication()
        nsapp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        nsapp.finishLaunching()
        self._install_status_item()
        self._start_dashboard()

        def _interrupt(_signum, _frame) -> None:
            _on_main(self._quit)

        signal.signal(signal.SIGINT, _interrupt)
        signal.signal(signal.SIGTERM, _interrupt)

        threading.Thread(target=self._load_and_arm, daemon=True).start()

        nsapp.run()
        _log("Stopped.")
        return 0

    def _load_and_arm(self) -> None:
        self._wanted_model = self.transcriber.model_key
        if not self._switch_model():
            _on_main(self._quit)
            return

        def start_monitor() -> None:
            try:
                self._monitor.start()
            except FnMonitorError as exc:
                _log(str(exc))
                self._quit()
                return
            _log("Ready. Hold Fn to dictate. Hold Cmd with Fn for commands.")

        _on_main(start_monitor)

    def model_status(self) -> dict[str, Any]:
        return {
            "model": self._wanted_model or self.transcriber.model_key,
            "active": self.transcriber.model_key,
            "status": self._model_status,
            "error": self._model_error,
            "phase": self._phase,
        }

    def request_model(self, model_key: str) -> dict[str, Any]:
        spec = _model_spec(model_key)
        if spec is None:
            raise TranscribeError("Unknown model.")
        key = spec["id"]
        self._wanted_model = key
        if key == self.transcriber.model_key and self.transcriber.is_ready() and self._model_status == "ready":
            return self.model_status()
        self._model_status = "loading"
        self._model_error = ""
        threading.Thread(target=self._switch_model, daemon=True).start()
        return self.model_status()

    def _switch_model(self) -> bool:
        from sonoscribe.settings import update_settings

        with self._model_lock:
            while True:
                key = self._wanted_model
                spec = _model_spec(key)
                if spec is None:
                    self._model_status = "error"
                    self._model_error = "Unknown model."
                    return False
                if (
                    spec["id"] == self.transcriber.model_key
                    and self.transcriber.is_ready()
                    and self._model_status == "ready"
                ):
                    return True
                self._model_status = "loading"
                self._model_error = ""
                _log(f"Loading Whisper model ({spec['label']})…")
                try:
                    self.transcriber.set_model(spec["id"], spec.get("path"))
                except Exception as exc:  # noqa: BLE001
                    message = friendly_load_error(exc)
                    self._model_error = message
                    _log(f"Failed to load Whisper: {message}")
                    if self.transcriber.is_ready():
                        self._wanted_model = self.transcriber.model_key
                        self._model_status = "error"
                        return True
                    if spec["id"] != DEFAULT_MODEL:
                        fallback = _model_spec(DEFAULT_MODEL)
                        if fallback is not None:
                            try:
                                self.transcriber.set_model(fallback["id"], fallback.get("path"))
                                self._wanted_model = fallback["id"]
                                update_settings({"model": fallback["id"]})
                                self._model_status = "error"
                                return True
                            except Exception:
                                pass
                    self._model_status = "error"
                    return False
                update_settings({"model": spec["id"]})
                self._model_status = "ready"
                if self._wanted_model == spec["id"]:
                    return True

    def _start_dashboard(self) -> None:
        server = DashboardServer(
            stats=self.stats,
            pick_path=self._pick_path,
            pick_app=self._pick_app,
            start_key_capture=self._start_key_capture,
            stop_key_capture=self._stop_key_capture,
            drain_key_capture=self._key_capture.drain,
            set_model=self.request_model,
            model_status=self.model_status,
        )
        try:
            server.start()
        except OSError as exc:
            _log(f"Dashboard unavailable: {exc}")
            if self._dashboard_item is not None:
                self._dashboard_item.setEnabled_(False)
            return
        self._dashboard = server
        if self._dashboard_item is not None:
            self._dashboard_item.setEnabled_(True)
        set_brief_notice(lambda run: _on_main(lambda: self._on_brief_notice(run)))
        set_brief_insert(lambda run: _on_main(lambda: self._insert_brief_run(run)))
        _log(f"Dashboard {server.url}")
        threading.Thread(target=self._pull_library, daemon=True).start()
        threading.Thread(target=self._sync_loop, daemon=True).start()
        threading.Thread(target=self._scribe_loop, daemon=True).start()

    def _pull_library(self) -> None:
        from sonoscribe.sync import SyncError, pull

        try:
            result = pull()
        except SyncError as exc:
            _log(f"Sync: {exc.message}")
            return
        if result.get("changed"):
            _log("Sync: library updated from the cloud")

    def _sync_loop(self) -> None:
        from sonoscribe.settings import load_settings
        from sonoscribe.sync import SyncError, pull

        waited = 0
        while not self._quitting:
            time.sleep(5)
            sync = load_settings().get("sync") or {}
            try:
                interval = int(sync.get("interval_sec") or 0)
            except (TypeError, ValueError):
                interval = 0
            if not sync.get("enabled") or interval <= 0:
                waited = 0
                continue
            waited += 5
            if waited < interval:
                continue
            waited = 0
            try:
                result = pull()
            except SyncError as exc:
                _log(f"Sync: {exc.message}")
                continue
            if result.get("changed"):
                _log("Sync: library updated from the cloud")

    def _open_dashboard(self, view: str = "", *, force: bool = False) -> None:
        if self._dashboard is None:
            _log("Dashboard is not running.")
            return
        if view:
            self._dashboard.request_focus(view)
        if not force and self._dashboard.client_open():
            return
        url = self._dashboard.url
        if view:
            url = url.rstrip("/") + f"/#{view}"
        _on_main(lambda: self._reveal_dashboard(url))

    def _reveal_dashboard(self, url: str) -> None:
        try:
            from AppKit import NSWorkspace

            nsurl = NSURL.URLWithString_(url)
            if nsurl is not None and NSWorkspace.sharedWorkspace().openURL_(nsurl):
                return
        except Exception:
            pass
        subprocess.run(["open", url], check=False)

    def _pick_path(self) -> str | None:
        chosen: list[str | None] = [None]

        def run() -> None:
            panel = NSOpenPanel.openPanel()
            panel.setCanChooseFiles_(True)
            panel.setCanChooseDirectories_(True)
            panel.setAllowsMultipleSelection_(False)
            if panel.runModal() == NSModalResponseOK:
                urls = panel.URLs()
                if urls:
                    chosen[0] = str(urls[0].path())

        self._call_main(run)
        return chosen[0]

    def _pick_app(self) -> dict[str, str] | None:
        chosen: list[dict[str, str] | None] = [None]

        def run() -> None:
            panel = NSOpenPanel.openPanel()
            panel.setCanChooseFiles_(True)
            panel.setCanChooseDirectories_(False)
            panel.setAllowsMultipleSelection_(False)
            panel.setTreatsFilePackagesAsDirectories_(False)
            panel.setAllowedFileTypes_(["app"])
            panel.setDirectoryURL_(NSURL.fileURLWithPath_("/Applications"))
            panel.setMessage_("Choose an application")
            if panel.runModal() == NSModalResponseOK:
                urls = panel.URLs()
                if urls:
                    chosen[0] = read_app(Path(str(urls[0].path())))

        self._call_main(run)
        return chosen[0]

    def _start_key_capture(self) -> dict:
        out: dict = {}

        def run() -> None:
            out.update(self._key_capture.start())

        self._call_main(run)
        return out or {"ok": False, "native": False}

    def _stop_key_capture(self) -> dict:
        out: dict = {}

        def run() -> None:
            out.update(self._key_capture.stop())

        self._call_main(run)
        return out or {"ok": True, "native": False, "keys": [], "stopped": False}

    def _quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        _log("Quitting…")
        set_brief_notice(None)
        set_brief_insert(None)
        try:
            self._dismiss_brief_notice()
        except Exception:
            pass
        try:
            self._monitor.stop()
        except Exception:
            pass
        try:
            self._key_capture.stop()
        except Exception:
            pass
        try:
            self.recorder.stop()
        except Exception:
            pass
        try:
            self.transcriber.close()
        except Exception:
            pass
        if self._dashboard is not None:
            try:
                self._dashboard.stop()
            except Exception:
                pass
        NSApplication.sharedApplication().terminate_(None)

    def _install_status_item(self) -> None:
        from AppKit import (
            NSMenu,
            NSMenuItem,
            NSSquareStatusItemLength,
            NSStatusBar,
            NSVariableStatusItemLength,
        )

        target = _StatusMenuTarget.alloc().init()
        target._owner = self
        self._status_target = target

        image = self._status_image()
        length = NSSquareStatusItemLength if image is not None else NSVariableStatusItemLength
        item = NSStatusBar.systemStatusBar().statusItemWithLength_(length)
        button = item.button()
        if button is not None:
            if image is not None:
                button.setImage_(image)
                button.setTitle_("")
            else:
                button.setTitle_("Sonoscribe")
            button.setToolTip_("Sonoscribe")
        elif image is None:
            item.setTitle_("Sonoscribe")

        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)

        dash = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Dashboard", "dashboard:", "")
        dash.setTarget_(target)
        dash.setEnabled_(False)
        menu.addItem_(dash)
        self._dashboard_item = dash

        menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "quit:", "")
        quit_item.setTarget_(target)
        quit_item.setEnabled_(True)
        menu.addItem_(quit_item)

        item.setMenu_(menu)
        if button is not None:
            button.setMenu_(menu)

        self._status_item = item
        self._status_menu = menu

    def _status_image(self):
        from AppKit import NSImage, NSMakeSize

        from sonoscribe.runtime import resource_path

        path = resource_path("StatusItem@2x.png")
        if not path.is_file():
            path = resource_path("StatusItem.png")
        if not path.is_file():
            return None
        image = NSImage.alloc().initWithContentsOfFile_(str(path))
        if image is None:
            return None
        image.setTemplate_(True)
        image.setSize_(NSMakeSize(18.0, 18.0))
        return image

    def on_begin(self) -> None:
        with self._lock:
            if self._phase != "idle":
                return
            if not accessibility_granted() and not self.copy_only:
                _log("Accessibility needed — grant access and restart.")
                return
            try:
                self.recorder.start()
            except RecorderError as exc:
                _log(str(exc))
                return
            self._session += 1
            self._slice_start = 0
            self._in_command = False
            self._used_command = False
            self._command_frontmost = None
            self._command_preroll = np.zeros(0, dtype=np.float32)
            self._want_idle = False
            self._hold_started = time.monotonic()
            self._phase = "recording"
            _log("Listening — hold Cmd for commands, release Fn to finish")

    def on_command_begin(self) -> None:
        if self._dashboard is not None and self._dashboard.test_listening():
            return
        snapped = _safe_frontmost()
        with self._lock:
            if self._phase != "recording" or self._in_command:
                return
            leftover, end = self.recorder.snapshot(self._slice_start)
            self._slice_start = end
            self._in_command = True
            self._used_command = True
            self._command_frontmost = snapped
            preroll, dictate = take_command_preroll(leftover)
            self._command_preroll = preroll
            if dictate is not None:
                self._enqueue_locked("dictate", dictate, self._session)
            _log("Command mode")

    def on_command_end(self) -> None:
        with self._lock:
            if self._phase != "recording" or not self._in_command:
                return
            samples, end = self.recorder.snapshot(self._slice_start)
            self._slice_start = end
            self._in_command = False
            samples = attach_preroll(self._command_preroll, samples)
            self._command_preroll = np.zeros(0, dtype=np.float32)
            self._enqueue_locked("command", samples, self._session, self._command_frontmost)
            _log("Dictating")

    def on_cancel(self) -> None:
        with self._lock:
            if self._phase == "recording":
                self.recorder.stop()
                _log("Cancelled")
            self._session += 1
            self._in_command = False
            self._command_frontmost = None
            self._command_preroll = np.zeros(0, dtype=np.float32)
            self._hold_started = None
            self._want_idle = True
            self._phase = "busy" if self._pending else "idle"

    def on_end(self) -> None:
        with self._lock:
            if self._phase != "recording":
                return
            elapsed = time.monotonic() - (self._hold_started or 0)
            leftover, _end = self.recorder.snapshot(self._slice_start)
            kind = "command" if self._in_command else "dictate"
            if kind == "command":
                leftover = attach_preroll(self._command_preroll, leftover)
            used_command = self._used_command
            session = self._session
            frontmost = self._command_frontmost if kind == "command" else None
            self.recorder.stop()
            self._in_command = False
            self._command_frontmost = None
            self._command_preroll = np.zeros(0, dtype=np.float32)
            self._hold_started = None
            self._slice_start = 0
            self._want_idle = True
            too_short = elapsed < MIN_HOLD_SECONDS and not used_command
            if too_short:
                self._phase = "busy" if self._pending else "idle"
                _log("Discarded (too short)")
                return
            self._enqueue_locked(kind, leftover, session, frontmost)
            self._phase = "busy" if self._pending else "idle"

    def _enqueue_locked(
        self,
        kind: str,
        samples: np.ndarray,
        session: int,
        frontmost: dict[str, str] | None = None,
    ) -> None:
        if samples.size < MINIMUM_SAMPLES:
            return
        self._pending += 1
        if kind == "command" and not frontmost:
            frontmost = _safe_frontmost()
        self._jobs.put(_Job(kind, samples, session, frontmost if kind == "command" else None))

    def _job_loop(self) -> None:
        while True:
            job = self._jobs.get()
            try:
                self._run_job(job)
            except Exception as exc:  # noqa: BLE001
                print(f"Error: {exc}", file=sys.stderr, flush=True)
            finally:
                with self._lock:
                    self._pending = max(0, self._pending - 1)
                    if self._want_idle and self._pending == 0 and self._phase != "recording":
                        self._phase = "idle"

    def _run_job(self, job: _Job) -> None:
        with self._lock:
            current = self._session
        if job.session != current:
            return
        _log("Transcribing…")
        kind = job.kind
        if kind == "command" and self._dashboard is not None and self._dashboard.test_listening():
            kind = "dictate"
        result = self.transcriber.transcribe(job.samples, mode=kind)
        with self._lock:
            if job.session != self._session:
                return
        heard = result.text.strip()
        _log(f"Heard: {heard or '(empty)'}")
        if kind == "command":
            self._run_command_text(heard, job.frontmost)
            return
        text = process(heard, remove_fillers=self.remove_fillers) if heard else ""
        if not text:
            _log("Nothing to paste")
            return
        seconds = float(job.samples.size) / float(SAMPLE_RATE)
        captured = bool(self._dashboard and self._dashboard.append_test(text))
        if not captured:
            self._call_main(lambda: self._paste(text))
        self.stats.record_dictation(text, seconds, model=self.transcriber.model_key)

    def _run_command_text(self, heard: str, frontmost: dict[str, str] | None = None) -> None:
        cleaned = prepare_command_text(heard)
        if not cleaned:
            return
        library = usable_library(load_library())
        hit = match_utterance(cleaned, library, frontmost=frontmost)
        if spoken_confirm(cleaned):
            _log("Scout confirm")
            return
        if hit.kind == "scout_incomplete":
            self._open_dashboard("scout")
            return
        if hit.kind == "scout":
            self._run_spoken_scout(hit)
            return
        if hit.kind == "scribe_incomplete":
            self._open_dashboard("scribe")
            return
        if hit.kind == "scribe":
            self._run_spoken_scribe(hit)
            return
        if hit.kind == "routine_incomplete":
            _log("Unknown command: routine")
            return
        if hit.kind == "unknown":
            _log(f"Unknown command: {hit.label}")
            return
        if hit.kind == "routine" and hit.routine is not None:
            routine = hit.routine
            bindings = dict(hit.bindings or {})
            variables = variable_map(library)
            if not skip_stats(routine):
                self.stats.record_routine(hit.label, model=self.transcriber.model_key)
            _log(f"Routine {hit.label}")

            def invoke(command: dict, keyboard: KeyboardState) -> str:
                result: list[str] = [""]

                def run() -> None:
                    result[0] = run_command(
                        command, keyboard, bindings=bindings, variables=variables
                    )

                self._call_main(run)
                return result[0]

            run_routine_steps(
                routine,
                lambda command_id: command_by_id(library, command_id),
                self.keyboard,
                _log,
                on_command=lambda command, label: None
                if skip_stats(command, routine)
                else self.stats.record_command(
                    label, str(command.get("type") or ""), model=self.transcriber.model_key
                ),
                invoke=invoke,
                bindings=bindings,
                variables=variables,
            )
            return
        if hit.kind == "command" and hit.command is not None:
            command = hit.command
            bindings = dict(hit.bindings or {})
            variables = variable_map(library)

            def run() -> None:
                label = run_command(
                    command, self.keyboard, bindings=bindings, variables=variables
                )
                _log(label)
                if not skip_stats(command):
                    self.stats.record_command(
                        label, str(command.get("type") or ""), model=self.transcriber.model_key
                    )

            self._call_main(run)

    def _run_spoken_scribe(self, hit) -> None:
        from sonoscribe.catalog import LibraryError
        from sonoscribe.dashboard.server import _push_in_background
        from sonoscribe.scribe.store import create_from_text

        text = str((hit.bindings or {}).get("text") or hit.label or "").strip()
        if not text:
            self._open_dashboard("scribe")
            return
        try:
            note = create_from_text(text)
        except LibraryError as exc:
            _log(str(exc))
            return
        _log(f"Scribe {note.get('title') or text}")
        _push_in_background()

    def _scribe_loop(self) -> None:
        while not self._quitting:
            time.sleep(15)
            _on_main(self._tick_reminders)

    def _tick_reminders(self) -> None:
        if self._notice_kind == "scribe" and self._pending_note_id:
            return
        from sonoscribe.scribe.store import due_vocanotes, mark_notified
        from sonoscribe.dashboard.server import _push_in_background

        notes = due_vocanotes()
        if not notes:
            return
        note = notes[0]
        ident = str(note.get("id") or "")
        if not ident:
            return
        marked = mark_notified(ident)
        if marked:
            note = marked
        _push_in_background()
        self._show_scribe_notice(note)

    def _open_pending_note(self, note_id: str = "") -> None:
        ident = str(note_id or self._pending_note_id or "").strip()
        self._dismiss_scribe_bubble(advance=True)
        if not ident:
            return
        if self._dashboard is not None:
            self._dashboard.request_open_note(ident)
        self._open_dashboard("scribe")

    def _done_pending_note(self, note_id: str = "") -> None:
        from sonoscribe.dashboard.server import _push_in_background
        from sonoscribe.scribe.parse import normalize_repeat
        from sonoscribe.scribe.store import advance_repeat, delete_vocanotes, get_vocanote

        ident = str(note_id or self._pending_note_id or "").strip()
        note = get_vocanote(ident) if ident else None
        self._dismiss_scribe_bubble()
        if not ident:
            return
        if note and normalize_repeat(note.get("repeat")):
            advance_repeat(ident)
        else:
            delete_vocanotes([ident])
        _push_in_background()
        _log(f"Scribe done {ident}")

    def _dismiss_scribe_bubble(self, advance: bool = False) -> None:
        ident = self._pending_note_id if self._notice_kind == "scribe" else ""
        if self._notice_kind == "scribe":
            self._notice_kind = ""
            self._pending_note_id = ""
        if advance and ident:
            try:
                from sonoscribe.scribe.parse import normalize_repeat
                from sonoscribe.scribe.store import advance_repeat, get_vocanote

                note = get_vocanote(ident)
                if note and normalize_repeat(note.get("repeat")):
                    advance_repeat(ident)
                    from sonoscribe.dashboard.server import _push_in_background

                    _push_in_background()
            except Exception:
                pass
        self._dismiss_brief_bubble()

    def _show_scribe_notice(self, note: dict[str, Any]) -> None:
        ident = str(note.get("id") or "").strip()
        if not ident:
            return
        title = reminder_title(note)
        self._dismiss_brief_bubble()
        self._notice_kind = "scribe"
        self._pending_note_id = ident
        self._present_status_bubble(
            kicker=reminder_kicker(),
            body=title,
            actions=(
                (reminder_done_label(), "doneScribeNote:"),
                (notice_later_label(), "closeScribeBubble:"),
            ),
            represented=ident,
            hit_action="openScribeNote:",
            holds=True,
        )

    def _run_spoken_scout(self, hit) -> None:
        bindings = hit.bindings or {}
        prompt = str(bindings.get("prompt") or "").strip()
        raw_ref = str(bindings.get("ref") or "").strip()
        if raw_ref == "":
            self._start_scout(prompt, source="prefix", frontmost=self._command_frontmost)
            return
        from sonoscribe.scout.store import resolve_scout_ref

        run = resolve_scout_ref(raw_ref)
        if run is None:
            if prompt:
                self._start_scout(
                    f"{raw_ref} {prompt}".strip(),
                    source="prefix",
                    frontmost=self._command_frontmost,
                )
            else:
                _log("no brief at that number")
                self._open_dashboard("scout")
            return
        ident = str(run.get("id") or "")
        sku = str(run.get("sku") or "")
        title = str(run.get("title") or prompt or "brief")
        set_scout_continue(ident)
        self._open_brief(ident)
        if prompt:
            self._start_scout(prompt, source="prefix", frontmost=self._command_frontmost)
            return
        _log(f"Scout {sku} {title}")
        self._open_dashboard("scout")

    def _open_brief(self, run_id: str) -> None:
        if self._dashboard is not None:
            self._dashboard.request_open_brief(run_id)

    def _on_brief_notice(self, run: dict[str, Any]) -> None:
        run_id = str(run.get("id") or "").strip()
        if not run_id:
            return
        if self._dashboard is not None and self._dashboard.scout_page_open():
            return
        self._pending_brief_id = run_id
        self._pending_open_url = str(run.get("open_url") or "")
        self._show_brief_notice(run)

    def _open_pending_brief(self, run_id: str = "") -> None:
        ident = str(run_id or self._pending_brief_id or "").strip()
        url = str(self._pending_open_url or "")
        if ident and not url:
            from sonoscribe.scout.store import get_run

            found = get_run(ident)
            url = str((found or {}).get("open_url") or "")
        self._dismiss_brief_notice()
        if not ident:
            return
        self._open_brief(ident)
        self._open_queued_page(url)
        self._open_dashboard("scout")

    def _open_queued_page(self, url: str) -> None:
        target = str(url or "").strip()
        if not target:
            return
        from sonoscribe.scout.tools import ToolError, open_queued_page

        try:
            open_queued_page(target)
        except ToolError:
            return

    def _show_brief_notice(self, run: dict[str, Any]) -> None:
        from AppKit import NSMenuItem

        from sonoscribe.scout.insert import notice_holds_bubble, notice_shows_insert

        status = str(run.get("status") or "")
        kicker = notice_kicker(status)
        body = notice_body(run)
        preview = notice_script_body(run)
        shows_insert = notice_shows_insert(run)
        holds = notice_holds_bubble(run)
        self._dismiss_brief_notice()
        self._notice_kind = "scout"
        self._pending_note_id = ""
        self._pending_brief_id = str(run.get("id") or "")
        self._pending_open_url = str(run.get("open_url") or "")
        menu = self._status_menu
        target = self._status_target
        if menu is not None and target is not None:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                notice_menu_label(run), "openBrief:", ""
            )
            item.setTarget_(target)
            item.setEnabled_(True)
            item.setRepresentedObject_(self._pending_brief_id)
            sep = NSMenuItem.separatorItem()
            menu.insertItem_atIndex_(item, 0)
            menu.insertItem_atIndex_(sep, 1)
            self._brief_menu_item = item
            self._brief_menu_sep = sep
        actions: tuple[tuple[str, str], ...] = ()
        if status == "needs_confirm":
            actions = (
                (notice_run_label(), "confirmBrief:"),
                (notice_cancel_label(), "cancelBrief:"),
            )
            holds = True
        elif shows_insert:
            actions = (
                (notice_insert_label(), "insertBrief:"),
                (notice_dismiss_label(), "closeBriefBubble:"),
            )
        self._present_status_bubble(
            kicker=kicker,
            body=body,
            preview=preview,
            actions=actions,
            represented=self._pending_brief_id,
            hit_action="openBrief:",
            holds=holds,
        )

    def _confirm_pending_brief(self, ok: bool) -> None:
        self._dismiss_brief_bubble()
        try:
            confirm_scout(bool(ok))
        except Exception as exc:
            _log(str(exc))

    def _present_status_bubble(
        self,
        *,
        kicker: str,
        body: str,
        preview: str = "",
        actions: tuple[tuple[str, str], ...] = (),
        represented: str,
        hit_action: str,
        holds: bool,
    ) -> None:
        import AppKit
        from AppKit import (
            NSButton,
            NSFont,
            NSMakeRect,
            NSMinYEdge,
            NSPopover,
            NSPopoverBehaviorTransient,
            NSTextField,
            NSView,
            NSViewController,
        )
        from sonoscribe.settings import load_settings

        target = self._status_target
        button = self._status_item.button() if self._status_item is not None else None
        if button is not None:
            button.setToolTip_(f"{kicker} · {body}")
        if button is None or target is None:
            return
        bezel = getattr(AppKit, "NSBezelStyleShadowlessSquare", None) or getattr(
            AppKit, "NSShadowlessSquareBezelStyle", 6
        )
        press = getattr(AppKit, "NSMomentaryLightButton", None) or getattr(
            AppKit, "NSButtonTypeMomentaryLight", 0
        )
        pad = 12
        kicker_h = 14
        body_h = 16
        action_h = 22 if actions else 0
        preview_lines = preview.count("\n") + 1 if preview else 0
        preview_h = preview_lines * 14 if preview else 0
        width = 360 if preview else 280
        height = pad + kicker_h + 8 + body_h + pad
        if preview:
            height += 8 + preview_h
        if actions:
            height += 8 + action_h
        sheet = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
        top = height - pad - kicker_h
        mark = NSTextField.alloc().initWithFrame_(NSMakeRect(pad, top, width - pad * 2, kicker_h))
        mark.setStringValue_(kicker)
        mark.setBezeled_(False)
        mark.setDrawsBackground_(False)
        mark.setEditable_(False)
        mark.setSelectable_(False)
        top -= 8 + body_h
        line = NSTextField.alloc().initWithFrame_(NSMakeRect(pad, top, width - pad * 2, body_h))
        line.setStringValue_(body)
        line.setBezeled_(False)
        line.setDrawsBackground_(False)
        line.setEditable_(False)
        line.setSelectable_(False)
        try:
            line.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
        except Exception:
            pass
        hit = NSButton.alloc().initWithFrame_(NSMakeRect(pad, top, width - pad * 2, body_h + 8 + kicker_h))
        hit.setButtonType_(press)
        hit.setBezelStyle_(bezel)
        hit.setBordered_(False)
        hit.setTitle_("")
        hit.setTarget_(target)
        hit.setAction_(hit_action)
        hit.setRepresentedObject_(represented)
        sheet.addSubview_(mark)
        sheet.addSubview_(line)
        sheet.addSubview_(hit)
        if preview:
            top -= 8 + preview_h
            block = NSTextField.alloc().initWithFrame_(NSMakeRect(pad, top, width - pad * 2, preview_h))
            block.setStringValue_(preview)
            block.setBezeled_(False)
            block.setDrawsBackground_(False)
            block.setEditable_(False)
            block.setSelectable_(False)
            try:
                block.setFont_(NSFont.userFixedPitchFontOfSize_(11))
                block.setUsesSingleLineMode_(False)
                cell = block.cell()
                if cell is not None:
                    cell.setWraps_(True)
            except Exception:
                pass
            sheet.addSubview_(block)
        buttons = []
        if actions:
            x = pad
            for label, action in actions:
                btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, pad, 64, action_h))
                btn.setButtonType_(press)
                btn.setBezelStyle_(bezel)
                btn.setBordered_(False)
                btn.setTitle_(label)
                btn.setTarget_(target)
                btn.setAction_(action)
                btn.setRepresentedObject_(represented)
                try:
                    btn.setFont_(NSFont.systemFontOfSize_(12))
                    btn.sizeToFit()
                    fitted = btn.frame()
                    btn.setFrame_(NSMakeRect(x, pad, max(fitted.size.width + 8, 44), action_h))
                except Exception:
                    pass
                sheet.addSubview_(btn)
                buttons.append(btn)
                x += btn.frame().size.width + 16
        self._brief_action_btns = buttons
        self._brief_insert_btn = buttons[0] if buttons else None
        self._brief_close_btn = buttons[1] if len(buttons) > 1 else None
        self._scribe_done_btn = buttons[0] if self._notice_kind == "scribe" and buttons else None
        host = NSViewController.alloc().init()
        host.setView_(sheet)
        pop = NSPopover.alloc().init()
        delegate = _BriefPopoverDelegate.alloc().init()
        delegate._owner = self
        pop.setContentViewController_(host)
        pop.setContentSize_(sheet.frame().size)
        defined = getattr(AppKit, "NSPopoverBehaviorApplicationDefined", None)
        if holds and defined is not None:
            pop.setBehavior_(defined)
        else:
            pop.setBehavior_(NSPopoverBehaviorTransient)
        pop.setAnimates_(not bool(load_settings().get("reduce_motion")))
        pop.setDelegate_(delegate)
        pop.showRelativeToRect_ofView_preferredEdge_(button.bounds(), button, NSMinYEdge)
        self._brief_popover_delegate = delegate
        self._brief_popover = pop
        if not holds:
            self._schedule_bubble_dismiss(self._pending_brief_id or self._pending_note_id)

    def _schedule_bubble_dismiss(self, run_id: str) -> None:
        self._bubble_token += 1
        token = self._bubble_token

        def wait() -> None:
            time.sleep(BUBBLE_SECONDS)
            _on_main(lambda: self._expire_brief_bubble(run_id, token))

        threading.Thread(target=wait, daemon=True).start()

    def _expire_brief_bubble(self, run_id: str, token: int) -> None:
        if token != self._bubble_token:
            return
        if str(self._pending_brief_id or "") != str(run_id or ""):
            return
        self._dismiss_brief_bubble()

    def _dismiss_brief_bubble(self) -> None:
        pop = self._brief_popover
        self._brief_popover = None
        self._brief_popover_delegate = None
        self._brief_insert_btn = None
        self._brief_close_btn = None
        self._brief_action_btns = []
        self._scribe_done_btn = None
        if self._notice_kind == "scribe":
            self._notice_kind = ""
            self._pending_note_id = ""
        if pop is not None:
            try:
                pop.setDelegate_(None)
                pop.performClose_(None)
            except Exception:
                pass
        button = self._status_item.button() if self._status_item is not None else None
        if button is not None:
            button.setToolTip_("Sonoscribe")

    def _dismiss_brief_notice(self) -> None:
        self._bubble_token += 1
        self._dismiss_brief_bubble()
        menu = self._status_menu
        item = self._brief_menu_item
        sep = self._brief_menu_sep
        self._brief_menu_item = None
        self._brief_menu_sep = None
        for piece in (item, sep):
            if menu is not None and piece is not None:
                try:
                    menu.removeItem_(piece)
                except Exception:
                    pass
        self._pending_brief_id = ""
        self._pending_open_url = ""

    def _start_scout(
        self,
        prompt: str,
        *,
        source: str = "prefix",
        frontmost: dict[str, str] | None = None,
    ) -> None:
        snapped = frontmost if frontmost is not None else self._command_frontmost
        try:
            start_scout(prompt, stats=self.stats, source=source, frontmost=snapped)
        except ScoutBusy:
            _log("a scout is already running")
            self._open_dashboard("scout")
            return
        except ScoutConfigError as exc:
            _log(str(exc))
            self._open_dashboard("scout")
            return
        _log(f"Scout {prompt}")

    def _insert_pending_brief(self, run_id: str = "") -> None:
        ident = str(run_id or self._pending_brief_id or "").strip()
        if not ident:
            return
        from sonoscribe.scout.store import get_run

        self._insert_brief_run(get_run(ident) or {"id": ident})

    def _insert_brief_run(self, run: dict[str, Any] | None) -> None:
        from sonoscribe.scout.insert import activate_frontmost, insert_text_from_run, needs_restore_app

        data = run if isinstance(run, dict) else {}
        text = insert_text_from_run(data)
        if not text:
            return
        self._dismiss_brief_bubble()
        front = data.get("frontmost") if isinstance(data.get("frontmost"), dict) else None
        if needs_restore_app(front, _safe_frontmost()) and activate_frontmost(front):
            threading.Timer(0.12, lambda: _on_main(lambda: self._paste(text))).start()
            return
        self._paste(text)

    def _paste(self, text: str) -> None:
        insert(text, copy_only=self.copy_only)
        if not self.copy_only:
            self.keyboard.last_inserted = text
        _log("Copied" if self.copy_only else "Pasted")

    def _call_main(self, fn) -> None:
        done = threading.Event()

        def wrap() -> None:
            try:
                fn()
            finally:
                done.set()

        _on_main(wrap)
        done.wait(timeout=120)
