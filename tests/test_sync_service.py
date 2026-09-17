import json

from sonoscribe.catalog import empty_library, save_library
from sonoscribe.settings import load_settings, update_settings
from sonoscribe.sync.crypto import decrypt, generate_keypair
from sonoscribe.sync.keychain import set_private_key
from sonoscribe.sync.cli import SyncError
from sonoscribe.sync.service import confirm_key, enable, import_key, pull, push, sign_in, status, validate


def test_enable_creates_key_and_waits(monkeypatch) -> None:
    monkeypatch.setattr(
        "sonoscribe.sync.service.probe_providers",
        lambda: {
            "aws": {"available": True, "message": ""},
            "gcs": {"available": False, "message": "no"},
            "azure": {"available": False, "message": "no"},
        },
    )
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: None)
    update_settings({"username": "studio"})
    result = enable({"provider": "aws", "bucket": "demo", "prefix": "lib"})
    assert result["created"] is True
    assert "BEGIN PRIVATE KEY" in result["private_key"]
    assert result["needs_confirm"] is True
    assert load_settings()["sync"]["enabled"] is False


def test_confirm_pushes_encrypted_library(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(tmp_path / "library.json"))
    monkeypatch.setenv("SONOSCRIBE_ROUTINES", str(tmp_path / "none.json"))
    from sonoscribe.catalog import clear_library_cache

    clear_library_cache()
    save_library(empty_library())
    uploads: list[bytes] = []
    monkeypatch.setattr(
        "sonoscribe.sync.service.probe_providers",
        lambda: {"aws": {"available": True, "message": ""}, "gcs": {"available": False, "message": ""}, "azure": {"available": False, "message": ""}},
    )
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: None)
    monkeypatch.setattr("sonoscribe.sync.service.upload", lambda _dest, payload: uploads.append(payload))
    update_settings({"username": "studio"})
    enable({"provider": "aws", "bucket": "demo"})
    result = confirm_key()
    assert result["sync"]["enabled"] is True
    assert uploads
    manifest = json.loads(uploads[-1].decode())
    assert manifest["public_key"].startswith("-----BEGIN PUBLIC KEY-----")
    pem = result.get("private_key")
    if not pem:
        from sonoscribe.sync.keychain import get_private_key

        pem = get_private_key()
    plain = json.loads(decrypt(pem, manifest["ciphertext"]).decode())
    assert manifest["v"] == 2
    assert plain["username"] == "studio"
    assert any(item["id"] == "kbd-enter" for item in plain["commands"])
    assert plain["devices"]


def test_newer_remote_wins(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(tmp_path / "library.json"))
    monkeypatch.setenv("SONOSCRIBE_ROUTINES", str(tmp_path / "none.json"))
    from sonoscribe.catalog import clear_library_cache, load_library

    clear_library_cache()
    local = empty_library()
    save_library(local)
    private_pem, public_pem = generate_keypair()
    set_private_key(private_pem, "local")
    update_settings(
        {
            "sync": {
                "enabled": True,
                "provider": "aws",
                "bucket": "demo",
                "needs_confirm": False,
            }
        }
    )
    remote_library = {
        "commands": [
            {
                "id": "kbd-only",
                "type": "keyboard",
                "name": "Only",
                "phrases": ["only"],
                "action": "enter",
            }
        ],
        "routines": [],
    }
    from sonoscribe.sync.crypto import encrypt

    remote = {
        "v": 1,
        "updated_at": "2099-01-01T00:00:00+00:00",
        "public_key": public_pem,
        "ciphertext": encrypt(public_pem, json.dumps(remote_library).encode()),
    }
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: json.dumps(remote).encode())
    result = pull()
    assert result["changed"] is True
    ids = {item["id"] for item in load_library()["commands"]}
    assert "kbd-only" in ids
    assert "kbd-enter" in ids


def test_enable_empty_bucket_needs_create(monkeypatch) -> None:
    monkeypatch.setattr(
        "sonoscribe.sync.service.probe_providers",
        lambda: {"aws": {"available": True, "message": ""}},
    )
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: None)
    result = enable({"provider": "aws", "bucket": "demo"})
    assert result["needs_create"] is True
    assert result["needs_join"] is False
    assert not result.get("private_key")
    assert load_settings()["sync"]["enabled"] is False
    assert load_settings()["sync"]["needs_create"] is True
    from sonoscribe.sync.keychain import has_private_key

    assert has_private_key() is False


def test_enable_empty_bucket_username_in_payload_mints(monkeypatch) -> None:
    monkeypatch.setattr(
        "sonoscribe.sync.service.probe_providers",
        lambda: {
            "aws": {"available": True, "message": ""},
            "gcs": {"available": False, "message": "no"},
            "azure": {"available": False, "message": "no"},
        },
    )
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: None)
    result = enable({"provider": "aws", "bucket": "demo", "username": "studio"})
    assert result["created"] is True
    assert result["needs_confirm"] is True
    assert "BEGIN PRIVATE KEY" in result["private_key"]
    assert load_settings()["username"] == "studio"
    assert load_settings()["sync"]["needs_create"] is False


def test_status_lists_providers(monkeypatch) -> None:
    monkeypatch.setattr(
        "sonoscribe.sync.service.probe_providers",
        lambda: {"aws": {"available": False, "message": "The AWS CLI isn’t on this Mac, so S3 isn’t available."}},
    )
    data = status()
    assert data["has_private_key"] is False
    assert "private_key" not in data


def test_confirm_resaves_pasted_pem(monkeypatch) -> None:
    monkeypatch.setattr(
        "sonoscribe.sync.service.probe_providers",
        lambda: {"aws": {"available": True, "message": ""}},
    )
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: None)
    monkeypatch.setattr("sonoscribe.sync.service.upload", lambda _dest, _payload: None)
    update_settings({"sync": {"provider": "aws", "bucket": "demo", "enabled": False}})
    private_pem, _public = generate_keypair()
    result = confirm_key(private_pem)
    assert result["has_private_key"] is True
    assert result["sync"]["enabled"] is True


def test_import_key_stores_pem() -> None:
    private_pem, _public = generate_keypair()
    data = import_key(private_pem)
    assert data["has_private_key"] is True
    assert data["fingerprint"]


def test_enable_asks_for_key_when_bucket_has_copy(monkeypatch) -> None:
    from sonoscribe.sync.crypto import encrypt
    from sonoscribe.sync.service import join

    private_pem, public_pem = generate_keypair()
    remote = {
        "v": 2,
        "updated_at": "2026-01-01T00:00:00+00:00",
        "public_key": public_pem,
        "ciphertext": encrypt(public_pem, json.dumps({"v": 2, "username": "studio", "devices": [], "commands": [], "routines": [], "stats": {}}).encode()),
    }
    monkeypatch.setattr(
        "sonoscribe.sync.service.probe_providers",
        lambda: {"aws": {"available": True, "message": ""}, "gcs": {"available": False, "message": ""}, "azure": {"available": False, "message": ""}},
    )
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: json.dumps(remote).encode())
    monkeypatch.setattr("sonoscribe.sync.service.upload", lambda _dest, _payload: None)
    result = enable({"provider": "aws", "bucket": "demo"})
    assert result["needs_key"] is True
    assert result["needs_join"] is True
    assert not result.get("private_key")
    assert load_settings()["sync"]["enabled"] is False
    assert load_settings()["sync"]["needs_key"] is True
    joined = join({"username": "studio", "private_key": private_pem})
    assert joined["sync"]["enabled"] is True
    assert joined["needs_key"] is False
    assert joined.get("push", {}).get("action") == "pushed"
    assert load_settings()["username"] == "studio"


def test_validate_checks_destination(monkeypatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        "sonoscribe.sync.service.probe_providers",
        lambda: {
            "aws": {"available": True, "message": ""},
            "gcs": {"available": False, "message": ""},
            "azure": {"available": False, "message": ""},
        },
    )
    monkeypatch.setattr(
        "sonoscribe.sync.service.verify_destination",
        lambda dest: seen.append(dest.bucket) or True,
    )
    result = validate({"provider": "aws", "bucket": "demo", "prefix": "lib"})
    assert result == {"ok": True, "exists": True}
    assert seen == ["demo"]


def test_validate_rejects_unavailable_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "sonoscribe.sync.service.probe_providers",
        lambda: {
            "aws": {"available": False, "message": "The AWS CLI isn’t on this Mac, so S3 isn’t available."},
            "gcs": {"available": False, "message": "no"},
            "azure": {"available": False, "message": "no"},
        },
    )
    try:
        validate({"provider": "aws", "bucket": "demo"})
        raise AssertionError("expected SyncError")
    except SyncError as exc:
        assert "AWS CLI" in exc.message


def test_validate_requires_bucket() -> None:
    try:
        validate({"provider": "aws", "bucket": ""})
        raise AssertionError("expected SyncError")
    except SyncError as exc:
        assert "bucket" in exc.message.lower()


def _ready_providers(monkeypatch) -> None:
    monkeypatch.setattr(
        "sonoscribe.sync.service.probe_providers",
        lambda: {
            "aws": {"available": True, "message": ""},
            "gcs": {"available": False, "message": ""},
            "azure": {"available": False, "message": ""},
        },
    )


def _remote_copy(public_pem: str, payload: dict) -> dict:
    from sonoscribe.sync.crypto import encrypt

    return {
        "v": 2,
        "updated_at": "2026-01-01T00:00:00+00:00",
        "public_key": public_pem,
        "ciphertext": encrypt(public_pem, json.dumps(payload).encode()),
    }


def test_join_rejects_wrong_key(monkeypatch) -> None:
    from sonoscribe.sync.service import join

    private_pem, public_pem = generate_keypair()
    other_pem, _other_pub = generate_keypair()
    remote = _remote_copy(
        public_pem,
        {"v": 2, "username": "studio", "devices": [], "commands": [], "routines": [], "stats": {}},
    )
    _ready_providers(monkeypatch)
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: json.dumps(remote).encode())
    monkeypatch.setattr("sonoscribe.sync.service.upload", lambda _dest, _payload: None)
    enable({"provider": "aws", "bucket": "demo"})
    try:
        join({"username": "studio", "private_key": other_pem})
        raise AssertionError("expected SyncError")
    except SyncError as exc:
        assert "key" in exc.message.lower()
    assert load_settings()["sync"]["enabled"] is False
    assert load_settings()["username"] == ""


def test_join_rejects_wrong_username(monkeypatch) -> None:
    from sonoscribe.sync.service import join

    private_pem, public_pem = generate_keypair()
    remote = _remote_copy(
        public_pem,
        {"v": 2, "username": "studio", "devices": [], "commands": [], "routines": [], "stats": {}},
    )
    _ready_providers(monkeypatch)
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: json.dumps(remote).encode())
    monkeypatch.setattr("sonoscribe.sync.service.upload", lambda _dest, _payload: None)
    enable({"provider": "aws", "bucket": "demo"})
    try:
        join({"username": "othername", "private_key": private_pem})
        raise AssertionError("expected SyncError")
    except SyncError as exc:
        assert "username" in exc.message.lower()
    assert load_settings()["sync"]["enabled"] is False
    assert load_settings()["username"] != "othername"


def test_join_same_serial_is_this_device(monkeypatch) -> None:
    from sonoscribe.sync.service import join

    this = load_settings()["device"]
    private_pem, public_pem = generate_keypair()
    remote = _remote_copy(
        public_pem,
        {
            "v": 2,
            "username": "studio",
            "devices": [
                {
                    "id": this["id"],
                    "serial": this.get("serial") or this["id"],
                    "name": "Studio",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            ],
            "commands": [],
            "routines": [],
            "stats": {},
        },
    )
    _ready_providers(monkeypatch)
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: json.dumps(remote).encode())
    monkeypatch.setattr("sonoscribe.sync.service.upload", lambda _dest, _payload: None)
    enable({"provider": "aws", "bucket": "demo"})
    result = join({"username": "STUDIO", "private_key": private_pem})
    assert result["device"] == "this"
    assert result["sync"]["enabled"] is True
    ids = [item["id"] for item in load_settings()["devices"]]
    assert ids.count(this["id"]) == 1


def test_push_failure_turns_sync_off(monkeypatch) -> None:
    private_pem, _public = generate_keypair()
    set_private_key(private_pem, "local")
    update_settings({"sync": {"enabled": True, "provider": "aws", "bucket": "demo"}})
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: None)

    def fail_upload(_dest, _payload):
        raise SyncError("AWS is here, but it isn’t signed in.", "Unable to locate credentials", "auth")

    monkeypatch.setattr("sonoscribe.sync.service.upload", fail_upload)
    try:
        push()
        raise AssertionError("expected SyncError")
    except SyncError:
        pass
    sync = load_settings()["sync"]
    assert sync["enabled"] is False
    assert sync["last_error"]["kind"] == "auth"
    assert "signed in" in sync["last_error"]["message"]


def test_pull_failure_turns_sync_off(monkeypatch) -> None:
    private_pem, _public = generate_keypair()
    set_private_key(private_pem, "local")
    update_settings({"sync": {"enabled": True, "provider": "gcs", "bucket": "demo"}})

    def fail_download(_dest):
        raise SyncError("Google Cloud is here, but it isn’t signed in.", "gcloud auth", "auth")

    monkeypatch.setattr("sonoscribe.sync.service.download", fail_download)
    try:
        pull()
        raise AssertionError("expected SyncError")
    except SyncError:
        pass
    sync = load_settings()["sync"]
    assert sync["enabled"] is False
    assert sync["last_error"]["kind"] == "auth"


def test_enable_push_error_does_not_ask_for_key(monkeypatch) -> None:
    _ready_providers(monkeypatch)
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: None)

    def fail_upload(_dest, _payload):
        raise SyncError("signed in", "no credentials", "auth")

    monkeypatch.setattr("sonoscribe.sync.service.upload", fail_upload)
    update_settings({"username": "studio"})
    enable({"provider": "aws", "bucket": "demo"})
    result = confirm_key()
    assert result["needs_key"] is False
    assert result["push"]["action"] == "error"
    assert load_settings()["sync"]["enabled"] is False
    assert load_settings()["sync"]["last_error"]["kind"] == "auth"


def test_sign_in_opens_provider_login(monkeypatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr("sonoscribe.sync.service.open_login_terminal", lambda cmd: seen.append(list(cmd)))
    update_settings({"sync": {"provider": "gcs", "bucket": "demo"}})
    result = sign_in({})
    assert result["ok"] is True
    assert result["command"] == "gcloud auth login"
    assert seen == [["gcloud", "auth", "login"]]


def test_join_new_serial_adds_this_device(monkeypatch) -> None:
    from sonoscribe.sync.service import join

    this = load_settings()["device"]
    private_pem, public_pem = generate_keypair()
    remote = _remote_copy(
        public_pem,
        {
            "v": 2,
            "username": "studio",
            "devices": [
                {
                    "id": "C02OTHERMAC01",
                    "serial": "C02OTHERMAC01",
                    "name": "Other",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            ],
            "commands": [],
            "routines": [],
            "stats": {},
        },
    )
    _ready_providers(monkeypatch)
    monkeypatch.setattr("sonoscribe.sync.service.download", lambda _dest: json.dumps(remote).encode())
    monkeypatch.setattr("sonoscribe.sync.service.upload", lambda _dest, _payload: None)
    enable({"provider": "aws", "bucket": "demo"})
    result = join({"username": "studio", "private_key": private_pem})
    assert result["device"] == "added"
    roster = {item["id"] for item in load_settings()["devices"]}
    assert this["id"] in roster
    assert "C02OTHERMAC01" in roster
