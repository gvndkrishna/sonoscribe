"""Hold Fn → record → Whisper → clean → paste. Fn+Cmd → commands."""

from __future__ import annotations

import queue
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSModalResponseOK,
    NSOpenPanel,
)
from Foundation import NSObject, NSOperationQueue, NSThread
import numpy as np
import objc

from sonoscribe.catalog import command_by_id, load_library, match_utterance
from sonoscribe.cleaner import process, strip_fillers
from sonoscribe.dashboard.server import DashboardServer
from sonoscribe.executor import KeyboardState, run_command, run_routine_steps
from sonoscribe.fn_monitor import FnMonitor, FnMonitorError
from sonoscribe.inserter import insert
from sonoscribe.lexicon import correct_product_name
from sonoscribe.permissions import (
    accessibility_granted,
    open_accessibility_settings,
    permission_help,
    prompt_accessibility,
)
from sonoscribe.recorder import MINIMUM_SAMPLES, SAMPLE_RATE, Recorder, RecorderError
from sonoscribe.stats import StatsStore
from sonoscribe.transcriber import Transcriber

MIN_HOLD_SECONDS = 0.25


def _log(message: str) -> None:
    print(message, flush=True)


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


class _StatusMenuTarget(NSObject):
    """Cocoa target for the menu extra. A Python function is not a valid ObjC selector."""

    _owner = objc.ivar()

    def dashboard_(self, _sender=None):
        owner = self._owner
        if owner is not None:
            owner._open_dashboard()

    def quit_(self, _sender=None):
        owner = self._owner
        if owner is not None:
            owner._quit()


class App:
    def __init__(self, model: str, remove_fillers: bool, copy_only: bool) -> None:
        self.remove_fillers = remove_fillers
        self.copy_only = copy_only
        self.recorder = Recorder()
        self.transcriber = Transcriber(model)
        self.stats = StatsStore()
        self.keyboard = KeyboardState()
        self._lock = threading.Lock()
        self._phase = "idle"
        self._hold_started: float | None = None
        self._slice_start = 0
        self._in_command = False
        self._used_command = False
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
        self._dashboard: DashboardServer | None = None
        self._quitting = False
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

        _log(f"Loading Whisper model ({self.transcriber.model_key})…")
        threading.Thread(target=self._load_and_arm, daemon=True).start()

        nsapp.run()
        _log("Stopped.")
        return 0

    def _load_and_arm(self) -> None:
        try:
            self.transcriber.load()
        except Exception as exc:  # noqa: BLE001
            _log(f"Failed to load Whisper: {exc}")
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

    def _start_dashboard(self) -> None:
        server = DashboardServer(stats=self.stats, pick_path=self._pick_path)
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
        _log(f"Dashboard {server.url}")

    def _open_dashboard(self) -> None:
        if self._dashboard is None:
            _log("Dashboard is not running.")
            return
        subprocess.run(["open", self._dashboard.url], check=False)

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

    def _quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        _log("Quitting…")
        try:
            self._monitor.stop()
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
        from AppKit import NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength

        target = _StatusMenuTarget.alloc().init()
        target._owner = self
        self._status_target = target

        item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        button = item.button()
        if button is not None:
            button.setTitle_("Sonoscribe")
            button.setToolTip_("Dashboard or Quit")
        else:
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
            self._want_idle = False
            self._hold_started = time.monotonic()
            self._phase = "recording"
            _log("Listening — hold Cmd for commands, release Fn to finish")

    def on_command_begin(self) -> None:
        with self._lock:
            if self._phase != "recording" or self._in_command:
                return
            samples, end = self.recorder.snapshot(self._slice_start)
            self._slice_start = end
            self._in_command = True
            self._used_command = True
            self._enqueue_locked("dictate", samples, self._session)
            _log("Command mode")

    def on_command_end(self) -> None:
        with self._lock:
            if self._phase != "recording" or not self._in_command:
                return
            samples, end = self.recorder.snapshot(self._slice_start)
            self._slice_start = end
            self._in_command = False
            self._enqueue_locked("command", samples, self._session)
            _log("Dictating")

    def on_cancel(self) -> None:
        with self._lock:
            if self._phase == "recording":
                self.recorder.stop()
                _log("Cancelled")
            self._session += 1
            self._in_command = False
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
            used_command = self._used_command
            session = self._session
            self.recorder.stop()
            self._in_command = False
            self._hold_started = None
            self._slice_start = 0
            self._want_idle = True
            too_short = elapsed < MIN_HOLD_SECONDS and not used_command
            if too_short:
                self._phase = "busy" if self._pending else "idle"
                _log("Discarded (too short)")
                return
            self._enqueue_locked(kind, leftover, session)
            self._phase = "busy" if self._pending else "idle"

    def _enqueue_locked(self, kind: str, samples: np.ndarray, session: int) -> None:
        if samples.size < MINIMUM_SAMPLES:
            return
        self._pending += 1
        self._jobs.put(_Job(kind, samples, session))

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
        result = self.transcriber.transcribe(job.samples)
        with self._lock:
            if job.session != self._session:
                return
        heard = result.text.strip()
        _log(f"Heard: {heard or '(empty)'}")
        if job.kind == "command":
            self._run_command_text(heard)
            return
        text = process(heard, remove_fillers=self.remove_fillers) if heard else ""
        if not text:
            _log("Nothing to paste")
            return
        seconds = float(job.samples.size) / float(SAMPLE_RATE)
        self._call_main(lambda: self._paste(text))
        self.stats.record_dictation(text, seconds)

    def _run_command_text(self, heard: str) -> None:
        cleaned = " ".join(strip_fillers(correct_product_name(heard)).split())
        if not cleaned:
            return
        library = load_library()
        hit = match_utterance(cleaned, library)
        if hit.kind == "routine_incomplete":
            _log("Unknown command: routine")
            return
        if hit.kind == "unknown":
            _log(f"Unknown command: {hit.label}")
            return
        if hit.kind == "routine" and hit.routine is not None:
            routine = hit.routine
            self.stats.record_routine(hit.label)
            _log(f"Routine {hit.label}")

            def invoke(command: dict, keyboard: KeyboardState) -> str:
                result: list[str] = [""]

                def run() -> None:
                    result[0] = run_command(command, keyboard)

                self._call_main(run)
                return result[0]

            run_routine_steps(
                routine,
                lambda command_id: command_by_id(library, command_id),
                self.keyboard,
                _log,
                on_command=lambda _command, label: self.stats.record_command(label),
                invoke=invoke,
            )
            return
        if hit.kind == "command" and hit.command is not None:
            command = hit.command

            def run() -> None:
                label = run_command(command, self.keyboard)
                _log(label)
                self.stats.record_command(label)

            self._call_main(run)

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
