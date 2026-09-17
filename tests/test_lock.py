import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sonoscribe.catalog import (
    ConfirmRequired,
    LibraryError,
    apply_library_update,
    empty_library,
    public_library,
    skip_stats,
    validate_library,
)
from sonoscribe.dashboard.server import DashboardServer
from sonoscribe.lock import LockController, hash_pin, verify_pin
from sonoscribe.stats import StatsStore


def _call(url: str, method: str = "GET", data=None, token: str | None = None):
    headers = {}
    raw = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        raw = json.dumps(data).encode()
    if token:
        headers["Cookie"] = f"ss_lock={token}"
    request = Request(url, data=raw, method=method, headers=headers)
    try:
        with urlopen(request) as response:
            return response.status, json.loads(response.read().decode())
    except HTTPError as exc:
        body = json.loads(exc.read().decode()) if exc.fp else {}
        return exc.code, body


def _secret_cmd() -> dict:
    return {
        "id": "cmd-secret",
        "type": "keyboard",
        "name": "Secret enter",
        "phrases": ["secret enter please"],
        "action": "enter",
        "secret": True,
    }


def test_pin_hash_never_stores_plaintext() -> None:
    blob = hash_pin("1234")
    assert "1234" not in blob
    assert verify_pin("1234", blob)
    assert not verify_pin("0000", blob)


def test_skip_stats_for_secret_items() -> None:
    assert skip_stats({"secret": True})
    assert skip_stats({"secret": False}, {"secret": True})
    assert not skip_stats({"name": "Enter"})


def test_public_library_strips_secrets() -> None:
    library = validate_library(
        {
            "commands": empty_library()["commands"] + [_secret_cmd()],
            "routines": [
                {
                    "id": "rtn-secret",
                    "name": "hidden routine",
                    "phrases": [],
                    "steps": [{"command_id": "kbd-enter", "delay_ms": 0}],
                    "secret": True,
                }
            ],
            "variables": [
                {
                    "id": "var-secret",
                    "name": "hush",
                    "value": "quiet",
                    "secret": True,
                }
            ],
        }
    )
    public = public_library(library)
    assert all(not item.get("secret") for item in public["commands"])
    assert all(not item.get("secret") for item in public["routines"])
    assert all(not item.get("secret") for item in public["variables"])
    assert any(item["id"] == "cmd-secret" for item in library["commands"])
    assert any(item["id"] == "var-secret" for item in library["variables"])


def test_put_without_secrets_keeps_them() -> None:
    current = validate_library(
        {
            "commands": empty_library()["commands"] + [_secret_cmd()],
            "routines": [],
            "variables": [{"id": "var-secret", "name": "hush", "value": "quiet", "secret": True}],
        }
    )
    incoming = {
        "commands": [item for item in current["commands"] if not item.get("secret")],
        "routines": [],
        "variables": [],
    }
    saved = apply_library_update(current, incoming, revealed=False, confirmed=False, lock_on=True)
    assert any(item["id"] == "cmd-secret" and item.get("secret") for item in saved["commands"])
    assert any(item["id"] == "var-secret" and item.get("secret") for item in saved["variables"])


def test_creating_secret_requires_lock_and_confirm() -> None:
    current = empty_library()
    incoming = {"commands": current["commands"] + [_secret_cmd()], "routines": []}
    try:
        apply_library_update(current, incoming, revealed=False, confirmed=True, lock_on=False)
        raise AssertionError("expected lock error")
    except LibraryError as exc:
        assert "lock" in str(exc).lower()
    try:
        apply_library_update(current, incoming, revealed=False, confirmed=False, lock_on=True)
        raise AssertionError("expected confirm")
    except ConfirmRequired:
        pass
    saved = apply_library_update(current, incoming, revealed=False, confirmed=True, lock_on=True)
    assert any(item.get("secret") for item in saved["commands"])


def test_lock_setup_unlock_wrong_pin_and_timeout() -> None:
    stats = StatsStore()
    server = DashboardServer(stats, port=0)
    clock = {"t": 0.0}
    server.lock = LockController(clock=lambda: clock["t"])
    server.start()
    try:
        status, body = _call(server.url + "api/lock/status")
        assert status == 200
        assert body["enabled"] is False
        assert body["unlocked"] is True
        status, body = _call(server.url + "api/lock/setup", "POST", {"pin": "1234", "timeout_sec": 300})
        assert status == 200
        token = body["token"]
        assert body["enabled"] is True
        assert body["method"] == "pin"
        status, body = _call(server.url + "api/library")
        assert status == 401
        assert body["code"] == "locked"
        status, body = _call(server.url + "api/lock/unlock", "POST", {"pin": "0000"})
        assert status == 401
        status, body = _call(server.url + "api/lock/unlock", "POST", {"pin": "1234"})
        assert status == 200
        token = body["token"]
        status, body = _call(server.url + "api/library", token=token)
        assert status == 200
        clock["t"] = 301
        status, body = _call(server.url + "api/library", token=token)
        assert status == 401
        assert body["code"] == "locked"
    finally:
        server.stop()


def test_username_and_sync_enable_require_confirm() -> None:
    stats = StatsStore()
    server = DashboardServer(stats, port=0)
    server.start()
    try:
        status, body = _call(server.url + "api/lock/setup", "POST", {"pin": "4242"})
        token = body["token"]
        status, body = _call(server.url + "api/account", "PUT", {"username": "studio"}, token=token)
        assert status == 401
        assert body["code"] == "confirm"
        status, body = _call(server.url + "api/lock/confirm", "POST", {"pin": "4242"}, token=token)
        assert status == 200
        assert body["confirmed"] is True
        status, body = _call(server.url + "api/account", "PUT", {"username": "studio"}, token=token)
        assert status == 200
        assert body["username"] == "studio"
        _call(server.url + "api/lock/lock", "POST", {}, token=token)
        status, body = _call(server.url + "api/lock/unlock", "POST", {"pin": "4242"})
        token = body["token"]
        status, body = _call(server.url + "api/sync/enable", "POST", {"provider": "gcs", "bucket": "x"}, token=token)
        assert status == 401
        assert body["code"] == "confirm"
        _call(server.url + "api/lock/confirm", "POST", {"pin": "4242"}, token=token)
        status, body = _call(
            server.url + "api/sync/enable",
            "POST",
            {"provider": "gcs", "bucket": "bucket"},
            token=token,
        )
        assert status != 401
    finally:
        server.stop()


def test_secret_library_get_put_and_reveal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(tmp_path / "library.json"))
    stats = StatsStore(tmp_path / "stats.json")
    server = DashboardServer(stats, port=0)
    server.start()
    try:
        status, body = _call(server.url + "api/lock/setup", "POST", {"pin": "9999"})
        token = body["token"]
        library = empty_library()
        library["commands"] = [item for item in library["commands"] if item["type"] == "keyboard"]
        library["commands"].append(_secret_cmd())
        library["variables"] = [{"id": "var-secret", "name": "hush", "value": "quiet", "secret": True}]
        status, body = _call(server.url + "api/library", "PUT", library, token=token)
        assert status == 401
        assert body["code"] == "confirm"
        _call(server.url + "api/lock/confirm", "POST", {"pin": "9999"}, token=token)
        status, body = _call(server.url + "api/library", "PUT", library, token=token)
        assert status == 200
        assert all(not item.get("secret") for item in body["commands"])
        assert all(not item.get("secret") for item in body.get("variables") or [])
        status, body = _call(server.url + "api/library", token=token)
        assert not any(item["id"] == "cmd-secret" for item in body["commands"])
        assert not any(item.get("id") == "var-secret" for item in body.get("variables") or [])
        public_payload = {
            "commands": [item for item in body["commands"] if item["id"] != "cmd-secret"],
            "routines": [],
            "variables": list(body.get("variables") or []),
        }
        status, body = _call(server.url + "api/library", "PUT", public_payload, token=token)
        assert status == 200
        _call(server.url + "api/lock/confirm", "POST", {"pin": "9999"}, token=token)
        status, body = _call(server.url + "api/lock/secrets", "POST", {"reveal": True}, token=token)
        assert status == 200
        assert body["secrets"] is True
        status, body = _call(server.url + "api/library", token=token)
        assert any(item["id"] == "cmd-secret" and item.get("secret") for item in body["commands"])
        assert any(item["id"] == "var-secret" and item.get("secret") for item in body["variables"])
    finally:
        server.stop()


def test_lock_now_clears_session() -> None:
    stats = StatsStore()
    server = DashboardServer(stats, port=0)
    server.start()
    try:
        status, body = _call(server.url + "api/lock/setup", "POST", {"pin": "1111"})
        token = body["token"]
        status, _body = _call(server.url + "api/library", token=token)
        assert status == 200
        _call(server.url + "api/lock/lock", "POST", {}, token=token)
        status, body = _call(server.url + "api/library", token=token)
        assert status == 401
        assert body["code"] == "locked"
    finally:
        server.stop()
