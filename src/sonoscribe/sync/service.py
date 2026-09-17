"""Enable, push, and pull the encrypted command library."""

from __future__ import annotations

import json
from typing import Any

from sonoscribe.catalog import load_library, save_library
from sonoscribe.device import is_alias_of, iso_now, this_device
from sonoscribe.profile import clean_username, username_error, usernames_match
from sonoscribe.settings import (
    KEYCHAIN_SCOPES,
    SYNC_PROVIDERS,
    load_settings,
    public_settings,
    sync_what,
    update_settings,
)
from sonoscribe.stats import StatsStore
from sonoscribe.sync.cli import (
    Destination,
    SyncError,
    download,
    login_command,
    open_login_terminal,
    probe_providers,
    upload,
    verify_destination,
)
from sonoscribe.sync.crypto import (
    CryptoError,
    decrypt,
    encrypt,
    fingerprint,
    generate_keypair,
    public_pem_from_private,
)
from sonoscribe.sync.keychain import (
    KeychainError,
    get_private_key,
    has_private_key,
    icloud_keychain_available,
    set_private_key,
)
from sonoscribe.sync.merge import empty_payload, merge_payloads, outgoing_library, parse_plain

__all__ = [
    "SyncError",
    "confirm_key",
    "disable",
    "enable",
    "import_key",
    "join",
    "pull",
    "push",
    "reveal_key",
    "set_keychain_scope",
    "sign_in",
    "status",
    "validate",
]


def status() -> dict[str, Any]:
    settings = load_settings()
    warning = ""
    try:
        pem = get_private_key()
    except KeychainError as exc:
        pem = None
        warning = str(exc)
    payload = public_settings(settings)
    payload["providers"] = probe_providers()
    payload["has_private_key"] = bool(pem)
    payload["fingerprint"] = fingerprint(pem) if pem else ""
    payload["icloud_keychain"] = icloud_keychain_available()
    if payload.get("keychain_scope") == "icloud" and not payload["icloud_keychain"]:
        payload["keychain_scope"] = "local"
    if warning and not payload["sync"].get("last_error"):
        payload["sync"] = {
            **payload["sync"],
            "last_error": {"message": warning, "details": ""},
        }
    return payload


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    dest = _destination_from(payload)
    providers = probe_providers()
    info = providers.get(dest.provider) or {}
    if not info.get("available"):
        message = str(info.get("message") or "That cloud option isn’t available on this Mac.")
        raise SyncError(message)
    exists = verify_destination(dest)
    return {"ok": True, "exists": bool(exists)}


def enable(payload: dict[str, Any]) -> dict[str, Any]:
    dest = _destination_from(payload)
    scope = _scope_from(payload)
    providers = probe_providers()
    info = providers.get(dest.provider) or {}
    if not info.get("available"):
        message = str(info.get("message") or "That cloud option isn’t available on this Mac.")
        raise SyncError(message)
    what_patch = payload.get("what") if isinstance(payload.get("what"), dict) else None
    sync_patch: dict[str, Any] = {
        **load_settings()["sync"],
        "provider": dest.provider,
        "bucket": dest.bucket,
        "prefix": dest.prefix,
        "account": dest.account,
        "project": dest.project,
        "last_error": None,
        "enabled": False,
        "needs_create": False,
        "needs_key": False,
        "needs_confirm": False,
    }
    if what_patch:
        sync_patch["what"] = what_patch
    update_settings({"keychain_scope": scope, "sync": sync_patch})
    remote = _read_remote(dest)
    pem = get_private_key()
    if remote is not None:
        if pem and _key_matches_remote(pem, remote):
            return _finish_with_key()
        _set_sync_flags(needs_key=True)
        return {
            "created": False,
            "needs_create": False,
            "needs_join": True,
            "needs_key": True,
            "needs_confirm": False,
            **status(),
        }
    username = _requested_username(payload)
    error = username_error(username)
    if error:
        _set_sync_flags(needs_create=True)
        if "username" in payload:
            raise SyncError(error)
        return {
            "created": False,
            "needs_create": True,
            "needs_join": False,
            "needs_key": False,
            "needs_confirm": False,
            **status(),
        }
    if clean_username(username) != clean_username(load_settings().get("username")):
        update_settings({"username": username})
    if not pem:
        private_pem, _public = generate_keypair()
        try:
            set_private_key(private_pem, scope)
        except KeychainError as exc:
            raise SyncError(str(exc)) from exc
        if scope == "icloud" and not icloud_keychain_available():
            update_settings({"keychain_scope": "local"})
        _set_sync_flags(needs_confirm=True)
        return {
            "created": True,
            "private_key": private_pem,
            "needs_create": False,
            "needs_join": False,
            "needs_confirm": True,
            "needs_key": False,
            **status(),
        }
    return _finish_with_key()


def confirm_key(pem: str | None = None) -> dict[str, Any]:
    text = (pem or "").strip()
    scope = str(load_settings().get("keychain_scope") or "local")
    try:
        if text:
            public_pem_from_private(text)
            set_private_key(text, scope)
        if not has_private_key():
            raise SyncError("There’s no private key on this Mac yet.")
    except CryptoError as exc:
        raise SyncError(str(exc)) from exc
    except KeychainError as exc:
        raise SyncError(str(exc)) from exc
    return _finish_with_key()


def import_key(pem: str) -> dict[str, Any]:
    text = (pem or "").strip()
    if not text:
        raise SyncError("Paste the private key.")
    try:
        public_pem_from_private(text)
    except CryptoError as exc:
        raise SyncError(str(exc)) from exc
    scope = str(load_settings().get("keychain_scope") or "local")
    try:
        set_private_key(text, scope)
    except KeychainError as exc:
        raise SyncError(str(exc)) from exc
    settings = load_settings()
    if settings["sync"].get("needs_key") or settings["sync"].get("needs_create"):
        update_settings({"sync": {**settings["sync"], "needs_confirm": False}})
        return status()
    if settings["sync"].get("bucket") and not username_error(settings.get("username")):
        return _finish_with_key()
    update_settings({"sync": {**settings["sync"], "needs_confirm": False, "needs_key": False, "needs_create": False}})
    return status()


def join(payload: dict[str, Any]) -> dict[str, Any]:
    username = clean_username((payload or {}).get("username"))
    error = username_error(username)
    if error:
        raise SyncError(error)
    pem = str((payload or {}).get("private_key") or (payload or {}).get("pem") or "").strip()
    if not pem:
        raise SyncError("Paste the private key.")
    try:
        public_pem_from_private(pem)
    except CryptoError as exc:
        raise SyncError(str(exc)) from exc
    settings = load_settings()
    if not (settings.get("sync") or {}).get("bucket"):
        raise SyncError("Save a destination first.")
    dest = _destination_from(settings["sync"])
    remote = _read_remote(dest)
    if remote is None:
        raise SyncError("No copy in this bucket.")
    if not _key_matches_remote(pem, remote):
        raise SyncError("Private key doesn't match.")
    remote_plain = _decrypt_remote(remote, pem)
    remote_name = clean_username(remote_plain.get("username"))
    if remote_name and not usernames_match(username, remote_name):
        raise SyncError("Username doesn't match.")
    canonical = remote_name or username
    scope = str(settings.get("keychain_scope") or "local")
    try:
        set_private_key(pem, scope)
    except KeychainError as exc:
        raise SyncError(str(exc)) from exc
    patch: dict[str, Any] = {"username": canonical}
    stamp = remote_plain.get("username_updated_at") if remote_name else None
    if stamp:
        patch["username_updated_at"] = stamp
    update_settings(patch)
    device = _device_status(remote_plain)
    result = _finish_with_key()
    result["device"] = device
    return result


def reveal_key() -> dict[str, str]:
    try:
        pem = get_private_key()
    except KeychainError as exc:
        raise SyncError(str(exc)) from exc
    if not pem:
        raise SyncError("There’s no private key on this Mac yet.")
    return {"private_key": pem, "fingerprint": fingerprint(pem)}


def set_keychain_scope(scope: str) -> dict[str, Any]:
    if scope not in KEYCHAIN_SCOPES:
        raise SyncError("Choose This Mac only, or sync with your other Macs.")
    pem = get_private_key()
    update_settings({"keychain_scope": scope})
    if pem:
        try:
            set_private_key(pem, scope)
        except KeychainError as exc:
            raise SyncError(str(exc)) from exc
    return status()


def disable() -> dict[str, Any]:
    sync = load_settings()["sync"]
    update_settings(
        {
            "sync": {
                **sync,
                "enabled": False,
                "last_error": None,
                "needs_create": False,
                "needs_key": False,
                "needs_confirm": False,
            }
        }
    )
    return status()


def push() -> dict[str, Any]:
    settings = load_settings()
    try:
        dest = _destination_from(settings["sync"])
        pem = _require_key()
        public_pem = public_pem_from_private(pem)
        updated_at = iso_now()
        remote_plain = _decrypt_remote(_read_remote(dest), pem)
        local_plain = _local_plain(settings)
        this_id = this_device(settings)["id"]
        what = sync_what(settings)
        merged = merge_payloads(local=local_plain, remote=remote_plain, this_id=this_id, what=what)
        upload_plain = {
            **merged,
            "commands": outgoing_library(merged["commands"], this_id),
            "routines": outgoing_library(merged["routines"], this_id),
            "variables": outgoing_library(merged.get("variables") or [], this_id),
        }
        box = encrypt(public_pem, json.dumps(upload_plain).encode("utf-8"))
        manifest = {
            "v": 2,
            "updated_at": updated_at,
            "public_key": public_pem,
            "ciphertext": box,
        }
        upload(dest, json.dumps(manifest).encode("utf-8"))
    except SyncError as exc:
        _record_error(exc)
        raise
    except CryptoError as exc:
        error = SyncError(str(exc))
        _record_error(error)
        raise error from exc
    _commit_plain(merged, what)
    _record_success(updated_at)
    return {"action": "pushed", "changed": True, **status()}


def pull() -> dict[str, Any]:
    settings = load_settings()
    if not settings["sync"].get("enabled"):
        return {"action": "skipped", "changed": False, **status()}
    try:
        dest = _destination_from(settings["sync"])
        pem = _require_key()
        remote_manifest = _read_remote(dest)
        if remote_manifest is None:
            return {"action": "empty", "changed": False, **status()}
        remote_plain = _decrypt_remote(remote_manifest, pem)
        local_plain = _local_plain(settings)
        this_id = this_device(settings)["id"]
        what = sync_what(settings)
        merged = merge_payloads(local=local_plain, remote=remote_plain, this_id=this_id, what=what)
        changed = _commit_plain(merged, what)
        _record_success(str(remote_manifest.get("updated_at") or iso_now()))
    except SyncError as exc:
        _record_error(exc)
        raise
    return {"action": "pulled", "changed": changed, **status()}


def _safe_push() -> dict[str, Any]:
    try:
        return push()
    except SyncError as exc:
        return {
            "action": "error",
            "changed": False,
            "error": exc.message,
            "details": exc.details,
            "kind": exc.kind,
        }


def sign_in(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    settings = load_settings()
    wanted = str(body.get("provider") or (settings.get("sync") or {}).get("provider") or "").strip()
    command = login_command(wanted)
    open_login_terminal(command)
    return {"ok": True, "command": " ".join(command), "provider": wanted, **status()}


def _finish_with_key() -> dict[str, Any]:
    pem = _require_key()
    settings = load_settings()
    dest = _destination_from(settings["sync"])
    remote = _read_remote(dest)
    if remote is not None and not _key_matches_remote(pem, remote):
        _set_sync_flags(needs_key=True)
        return {
            "needs_key": True,
            "needs_join": True,
            "needs_create": False,
            "push": {
                "action": "error",
                "changed": False,
                "error": "Private key doesn't match.",
            },
            **status(),
        }
    _set_sync_flags(enabled=True)
    pushed = _safe_push()
    if pushed.get("action") == "error":
        return {"needs_key": False, "needs_join": False, "needs_create": False, "push": pushed, **status()}
    return {
        "needs_key": False,
        "needs_join": False,
        "needs_create": False,
        "push": pushed,
        **status(),
    }


def _requested_username(payload: dict[str, Any]) -> str:
    if payload.get("username") not in (None, ""):
        return clean_username(payload.get("username"))
    return clean_username(load_settings().get("username"))


def _device_status(remote_plain: dict[str, Any] | None) -> str:
    this = this_device(load_settings())
    if not remote_plain:
        return "this"
    this_id = str(this.get("id") or "").strip()
    this_serial = str(this.get("serial") or this_id).strip()
    for item in remote_plain.get("devices") or []:
        item_id = str(item.get("id") or "").strip()
        if this_id and item_id == this_id:
            return "this"
        if is_alias_of(item, this):
            return "this"
        item_serial = str(item.get("serial") or item_id).strip()
        if this_serial and item_serial == this_serial:
            return "this"
    return "added"


def _set_sync_flags(
    *,
    enabled: bool = False,
    needs_key: bool = False,
    needs_confirm: bool = False,
    needs_create: bool = False,
) -> None:
    update_settings(
        {
            "sync": {
                **load_settings()["sync"],
                "enabled": enabled,
                "needs_key": needs_key,
                "needs_confirm": needs_confirm,
                "needs_create": needs_create,
            }
        }
    )


def _key_matches_remote(pem: str, remote: dict[str, Any]) -> bool:
    remote_pub = str(remote.get("public_key") or "").strip()
    if remote_pub:
        try:
            return fingerprint(pem) == fingerprint(remote_pub)
        except CryptoError:
            return False
    try:
        _decrypt_remote(remote, pem)
        return True
    except SyncError:
        return False


def _local_plain(settings: dict[str, Any]) -> dict[str, Any]:
    library = load_library()
    what = sync_what(settings)
    this = this_device(settings)
    payload = empty_payload()
    payload["username"] = str(settings.get("username") or "")
    payload["username_updated_at"] = settings.get("username_updated_at")
    payload["devices"] = list(settings.get("devices") or [this])
    payload["commands"] = list(library.get("commands") or [])
    payload["routines"] = list(library.get("routines") or [])
    payload["variables"] = list(library.get("variables") or [])
    if what.get("stats"):
        store = StatsStore()
        stats = store.remote_devices()
        stats[this["id"]] = store.export_blob()
        payload["stats"] = stats
    return payload


def _commit_plain(merged: dict[str, Any], what: dict[str, bool]) -> bool:
    settings = load_settings()
    this_id = this_device(settings)["id"]
    changed = False
    patch: dict[str, Any] = {}
    if what.get("profile", True):
        if merged.get("username") != settings.get("username"):
            changed = True
        patch["username"] = merged.get("username") or ""
        patch["username_updated_at"] = merged.get("username_updated_at")
        patch["devices"] = list(merged.get("devices") or [])
        changed = True
    if patch:
        update_settings(patch)
    if what.get("library", True):
        save_library(
            {
                "commands": merged.get("commands") or [],
                "routines": merged.get("routines") or [],
                "variables": merged.get("variables") or [],
            }
        )
        changed = True
    if what.get("stats"):
        StatsStore().apply_synced_stats(merged.get("stats") or {}, this_id)
        changed = True
    return changed


def _decrypt_remote(remote: dict[str, Any] | None, pem: str) -> dict[str, Any]:
    if remote is None:
        return empty_payload()
    try:
        plain = decrypt(pem, str(remote.get("ciphertext") or ""))
        return parse_plain(json.loads(plain.decode("utf-8")))
    except (CryptoError, json.JSONDecodeError, UnicodeError, ValueError) as exc:
        message = str(exc) if isinstance(exc, CryptoError) else "The cloud copy could not be read."
        raise SyncError(message) from exc


def _read_remote(dest: Destination) -> dict[str, Any] | None:
    try:
        raw = download(dest)
    except SyncError as exc:
        _record_error(exc)
        raise
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        error = SyncError("The cloud copy could not be read.")
        _record_error(error)
        raise error from exc
    if not isinstance(data, dict) or not data.get("ciphertext"):
        error = SyncError("The cloud copy could not be read.")
        _record_error(error)
        raise error
    return data


def _destination_from(raw: dict[str, Any]) -> Destination:
    provider = str(raw.get("provider") or "").strip()
    if provider not in SYNC_PROVIDERS:
        raise SyncError("Choose Amazon S3, Google Cloud, or Azure.")
    bucket = str(raw.get("bucket") or "").strip()
    if not bucket:
        raise SyncError("Add a bucket or container name.")
    account = str(raw.get("account") or "").strip()
    if provider == "azure" and not account:
        raise SyncError("Azure also needs a storage account name.")
    return Destination(
        provider=provider,
        bucket=bucket,
        prefix=str(raw.get("prefix") or "").strip().strip("/"),
        account=account,
        project=str(raw.get("project") or "").strip(),
    )


def _scope_from(raw: dict[str, Any]) -> str:
    scope = str(raw.get("keychain_scope") or load_settings().get("keychain_scope") or "local")
    if scope not in KEYCHAIN_SCOPES:
        return "local"
    return scope


def _require_key() -> str:
    pem = get_private_key()
    if not pem:
        raise SyncError("Add the private key from your other Mac, then try again.")
    return pem


def _record_success(when: str) -> None:
    update_settings({"sync": {**load_settings()["sync"], "last_sync_at": when, "last_error": None}})


def _record_error(exc: SyncError) -> None:
    error: dict[str, str] = {"message": exc.message, "details": exc.details}
    if exc.kind:
        error["kind"] = exc.kind
    update_settings(
        {
            "sync": {
                **load_settings()["sync"],
                "enabled": False,
                "last_error": error,
            }
        }
    )
