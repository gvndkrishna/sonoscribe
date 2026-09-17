"""This-Mac dashboard lock: 4-digit PIN in Keychain, in-memory session."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sonoscribe.settings import load_settings, update_settings
from sonoscribe.sync.keychain import delete_lock_secret, get_lock_secret, set_lock_secret

COOKIE_NAME = "ss_lock"
LOCK_TIMEOUTS = (300, 600, 900, 1800, 2700, 3600)
DEFAULT_TIMEOUT = 900
CONFIRM_SECONDS = 120
PIN_ROUNDS = 210_000
_PIN_RE = re.compile(r"^\d{4}$")


class LockError(Exception):
    def __init__(self, message: str, status: int = 401, code: str = "locked") -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def empty_lock() -> dict[str, Any]:
    return {"enabled": False, "method": "", "timeout_sec": DEFAULT_TIMEOUT}


def clean_lock(raw: Any) -> dict[str, Any]:
    data = empty_lock()
    if not isinstance(raw, dict):
        return data
    try:
        timeout = int(raw.get("timeout_sec"))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    if timeout in LOCK_TIMEOUTS:
        data["timeout_sec"] = timeout
    enabled = bool(raw.get("enabled"))
    method = str(raw.get("method") or "").strip()
    if enabled and method in {"", "pin"}:
        data["enabled"] = True
        data["method"] = "pin"
    return data


def lock_settings() -> dict[str, Any]:
    return clean_lock(load_settings().get("lock"))


def lock_enabled() -> bool:
    return bool(lock_settings().get("enabled"))


def pin_ok(pin: str) -> bool:
    return bool(_PIN_RE.fullmatch(str(pin or "")))


def hash_pin(pin: str, salt: bytes | None = None) -> str:
    if not pin_ok(pin):
        raise LockError("PIN must be 4 digits.", 400, "pin")
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, PIN_ROUNDS)
    return f"pbkdf2:sha256:{PIN_ROUNDS}:{salt.hex()}:{digest.hex()}"


def verify_pin(pin: str, blob: str) -> bool:
    if not pin_ok(pin) or not blob:
        return False
    parts = blob.split(":")
    if len(parts) != 5 or parts[0] != "pbkdf2" or parts[1] != "sha256":
        return False
    try:
        rounds = int(parts[2])
        salt = bytes.fromhex(parts[3])
        expected = bytes.fromhex(parts[4])
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(digest, expected)


def cookie_value(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME and value:
            return value
    return None


def set_cookie_header(token: str) -> str:
    return f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax"


def clear_cookie_header() -> str:
    return f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


def public_lock(session: LockSession | None = None, now: float | None = None) -> dict[str, Any]:
    cfg = lock_settings()
    stamp = time.monotonic() if now is None else now
    unlocked = (not cfg["enabled"]) or (session is not None)
    return {
        "enabled": bool(cfg["enabled"]),
        "method": cfg["method"],
        "timeout_sec": int(cfg["timeout_sec"]),
        "timeouts": list(LOCK_TIMEOUTS),
        "unlocked": unlocked,
        "secrets": (not cfg["enabled"]) or bool(session and session.secrets),
        "confirmed": bool(session and session.confirm_until > stamp),
    }


def _write_lock(*, enabled: bool, timeout_sec: int | None = None) -> dict[str, Any]:
    current = clean_lock(load_settings().get("lock"))
    if timeout_sec in LOCK_TIMEOUTS:
        current["timeout_sec"] = timeout_sec
    current["enabled"] = bool(enabled)
    current["method"] = "pin" if enabled else ""
    return update_settings({"lock": current})


@dataclass
class LockSession:
    token: str
    last_active: float
    secrets: bool = False
    confirm_until: float = 0.0


class LockController:
    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._guard = threading.Lock()
        self._session: LockSession | None = None

    def now(self) -> float:
        return self._clock()

    def status(self, token: str | None) -> dict[str, Any]:
        with self._guard:
            sess = self._alive_locked(token)
            return public_lock(sess, self.now())

    def require_unlocked(self, token: str | None) -> LockSession | None:
        if not lock_enabled():
            return None
        with self._guard:
            sess = self._alive_locked(token)
        if sess is None:
            raise LockError("Locked.", 401, "locked")
        return sess

    def require_confirm(self, token: str | None) -> LockSession | None:
        sess = self.require_unlocked(token)
        if not lock_enabled():
            return sess
        assert sess is not None
        if sess.confirm_until <= self.now():
            raise LockError("Confirm required.", 401, "confirm")
        return sess

    def activity(self, token: str | None) -> dict[str, Any]:
        with self._guard:
            sess = self._alive_locked(token)
            if sess is not None:
                sess.last_active = self.now()
            return public_lock(sess, self.now())

    def lock_now(self, _token: str | None = None) -> dict[str, Any]:
        with self._guard:
            self._session = None
            return public_lock(None, self.now())

    def setup(self, body: dict[str, Any], token: str | None) -> tuple[dict[str, Any], str]:
        cfg = lock_settings()
        if cfg["enabled"]:
            self.require_unlocked(token)
            current = str(body.get("current") or "")
            blob = get_lock_secret() or ""
            if not verify_pin(current, blob):
                raise LockError("Wrong PIN.", 401, "pin")
        pin = str(body.get("pin") or "")
        if not pin_ok(pin):
            raise LockError("PIN must be 4 digits.", 400, "pin")
        timeout = body.get("timeout_sec", cfg["timeout_sec"])
        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            timeout = cfg["timeout_sec"]
        if timeout not in LOCK_TIMEOUTS:
            timeout = cfg["timeout_sec"]
        set_lock_secret(hash_pin(pin))
        _write_lock(enabled=True, timeout_sec=timeout)
        sess = self._new_session()
        return public_lock(sess, self.now()), sess.token

    def disable(self, token: str | None) -> dict[str, Any]:
        self.require_unlocked(token)
        delete_lock_secret()
        _write_lock(enabled=False, timeout_sec=lock_settings()["timeout_sec"])
        with self._guard:
            self._session = None
        return public_lock(None, self.now())

    def set_timeout(self, timeout_sec: int, token: str | None) -> dict[str, Any]:
        self.require_unlocked(token)
        if timeout_sec not in LOCK_TIMEOUTS:
            raise LockError("Invalid auto-lock time.", 400, "timeout")
        cfg = lock_settings()
        _write_lock(enabled=cfg["enabled"], timeout_sec=timeout_sec)
        with self._guard:
            sess = self._alive_locked(token)
            return public_lock(sess, self.now())

    def unlock_pin(self, pin: str) -> tuple[dict[str, Any], str]:
        cfg = lock_settings()
        if not cfg["enabled"]:
            raise LockError("Lock is off.", 400, "lock")
        blob = get_lock_secret() or ""
        if not verify_pin(pin, blob):
            raise LockError("Wrong PIN.", 401, "locked")
        sess = self._new_session()
        return public_lock(sess, self.now()), sess.token

    def confirm_pin(self, pin: str, token: str | None) -> dict[str, Any]:
        sess = self.require_unlocked(token)
        blob = get_lock_secret() or ""
        if not verify_pin(pin, blob):
            raise LockError("Wrong PIN.", 401, "confirm")
        assert sess is not None
        with self._guard:
            if self._session is sess:
                sess.confirm_until = self.now() + CONFIRM_SECONDS
            return public_lock(sess, self.now())

    def set_secrets(self, reveal: bool, token: str | None) -> dict[str, Any]:
        sess = self.require_unlocked(token)
        if not lock_enabled():
            raise LockError("Set a lock first.", 400, "lock")
        assert sess is not None
        if reveal:
            self.require_confirm(token)
        with self._guard:
            if self._session is sess:
                sess.secrets = bool(reveal)
            return public_lock(sess, self.now())

    def secrets_open(self, token: str | None) -> bool:
        if not lock_enabled():
            return True
        with self._guard:
            sess = self._alive_locked(token)
            return bool(sess and sess.secrets)

    def _new_session(self) -> LockSession:
        sess = LockSession(token=secrets.token_hex(24), last_active=self.now())
        with self._guard:
            self._session = sess
        return sess

    def _alive_locked(self, token: str | None) -> LockSession | None:
        cfg = lock_settings()
        sess = self._session
        if not cfg["enabled"] or sess is None or not token or sess.token != token:
            return None
        if self.now() - sess.last_active > int(cfg["timeout_sec"]):
            self._session = None
            return None
        return sess
