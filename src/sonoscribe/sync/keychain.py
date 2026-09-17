"""macOS Keychain storage for the sync private key."""

from __future__ import annotations

import os
from typing import Any, Protocol

SERVICE = "sonoscribe.sync"
ACCOUNT = "private-key"
LOCK_SERVICE = "sonoscribe.lock"
LOCK_ACCOUNT = "unlock"
_ERR_MISSING_ENTITLEMENT = -34018
_icloud_ok: bool | None = None


class KeychainError(RuntimeError):
    pass


class KeychainStore(Protocol):
    def get(self) -> str | None: ...
    def set(self, pem: str, scope: str) -> None: ...
    def delete(self) -> None: ...


class MemoryKeychain:
    def __init__(self) -> None:
        self.pem: str | None = None
        self.scope: str = "local"
        self.lock_blob: str | None = None

    def get(self) -> str | None:
        return self.pem

    def set(self, pem: str, scope: str) -> None:
        self.pem = pem
        self.scope = scope if scope in {"local", "icloud"} else "local"

    def delete(self) -> None:
        self.pem = None

    def get_lock(self) -> str | None:
        return self.lock_blob

    def set_lock(self, blob: str) -> None:
        self.lock_blob = blob

    def delete_lock(self) -> None:
        self.lock_blob = None


class SecurityKeychain:
    def get(self) -> str | None:
        for query in _lookup_queries():
            status, data = _copy(query)
            if status in {_const("not_found"), _ERR_MISSING_ENTITLEMENT}:
                if status == _ERR_MISSING_ENTITLEMENT:
                    _mark_icloud_unavailable()
                continue
            if status != 0:
                raise KeychainError(_status_message("read", status))
            pem = _decode_secret(data)
            if pem:
                return pem
        return None

    def set(self, pem: str, scope: str) -> None:
        self.delete()
        wanted = "icloud" if scope == "icloud" and icloud_keychain_available() else "local"
        status, _result = _add(_item_attrs(pem, wanted))
        if wanted == "icloud" and status == _ERR_MISSING_ENTITLEMENT:
            _mark_icloud_unavailable()
            status, _result = _add(_item_attrs(pem, "local"))
        if status != 0:
            raise KeychainError(_status_message("save", status))
        if not self.get():
            raise KeychainError("Keychain accepted the key, but this Mac could not read it back.")

    def delete(self) -> None:
        for query in _delete_queries():
            status = _delete(query)
            if status == _ERR_MISSING_ENTITLEMENT:
                _mark_icloud_unavailable()
                continue
            if status not in {0, _const("not_found")}:
                raise KeychainError(_status_message("update", status))

    def get_lock(self) -> str | None:
        status, data = _copy(_lock_lookup_query())
        if status in {_const("not_found"), _ERR_MISSING_ENTITLEMENT}:
            return None
        if status != 0:
            raise KeychainError(_status_message("read", status))
        return _decode_secret(data)

    def set_lock(self, blob: str) -> None:
        self.delete_lock()
        status, _result = _add(_lock_item_attrs(blob))
        if status != 0:
            raise KeychainError(_status_message("save", status))
        if not self.get_lock():
            raise KeychainError("Keychain accepted the lock, but this Mac could not read it back.")

    def delete_lock(self) -> None:
        status = _delete(_lock_base_query())
        if status == _ERR_MISSING_ENTITLEMENT:
            return
        if status not in {0, _const("not_found")}:
            raise KeychainError(_status_message("update", status))


_store: KeychainStore | None = None
_consts: dict[str, Any] | None = None


def use_memory_keychain(store: MemoryKeychain | None = None) -> MemoryKeychain:
    global _store
    memory = store or MemoryKeychain()
    _store = memory
    return memory


def reset_keychain_store() -> None:
    global _store, _icloud_ok
    _store = None
    _icloud_ok = None


def icloud_keychain_available() -> bool:
    return _icloud_ok is not False


def _mark_icloud_unavailable() -> None:
    global _icloud_ok
    _icloud_ok = False


def get_private_key() -> str | None:
    pem = _backend().get()
    if not pem or not str(pem).strip():
        return None
    return str(pem)


def set_private_key(pem: str, scope: str) -> None:
    text = pem.strip()
    if not text:
        raise KeychainError("Private key is empty.")
    _backend().set(text, scope)


def delete_private_key() -> None:
    _backend().delete()


def has_private_key() -> bool:
    return get_private_key() is not None


def get_lock_secret() -> str | None:
    getter = getattr(_backend(), "get_lock", None)
    if getter is None:
        return None
    blob = getter()
    if not blob or not str(blob).strip():
        return None
    return str(blob)


def set_lock_secret(blob: str) -> None:
    text = blob.strip()
    if not text:
        raise KeychainError("Lock secret is empty.")
    setter = getattr(_backend(), "set_lock", None)
    if setter is None:
        raise KeychainError("Lock secret storage is unavailable.")
    setter(text)


def delete_lock_secret() -> None:
    deleter = getattr(_backend(), "delete_lock", None)
    if deleter is not None:
        deleter()


def _backend() -> KeychainStore:
    global _store
    if _store is not None:
        return _store
    if os.environ.get("SONOSCRIBE_KEYCHAIN") == "memory":
        _store = MemoryKeychain()
        return _store
    _load_security()
    _store = SecurityKeychain()
    return _store


def _base_query() -> dict[Any, Any]:
    return {
        _const("class"): _const("generic"),
        _const("service"): SERVICE,
        _const("account"): ACCOUNT,
    }


def _lock_base_query() -> dict[Any, Any]:
    return {
        _const("class"): _const("generic"),
        _const("service"): LOCK_SERVICE,
        _const("account"): LOCK_ACCOUNT,
    }


def _lock_lookup_query() -> dict[Any, Any]:
    return {
        **_lock_base_query(),
        _const("return_data"): True,
        _const("match_limit"): _const("match_one"),
    }


def _lock_item_attrs(blob: str) -> dict[Any, Any]:
    attrs: dict[Any, Any] = {
        _const("class"): _const("generic"),
        _const("service"): LOCK_SERVICE,
        _const("account"): LOCK_ACCOUNT,
        _const("label"): "Sonoscribe lock",
        _const("value"): blob.encode("utf-8"),
        _const("accessible"): _const("this_device"),
    }
    if _const("synchronizable") is not None:
        attrs[_const("synchronizable")] = False
    return attrs


def _item_attrs(pem: str, scope: str) -> dict[Any, Any]:
    attrs: dict[Any, Any] = {
        _const("class"): _const("generic"),
        _const("service"): SERVICE,
        _const("account"): ACCOUNT,
        _const("label"): "Sonoscribe sync key",
        _const("value"): pem.encode("utf-8"),
    }
    if scope == "icloud" and _const("synchronizable") is not None:
        attrs[_const("accessible")] = _const("after_unlock")
        attrs[_const("synchronizable")] = True
    else:
        attrs[_const("accessible")] = _const("this_device")
    return attrs


def _lookup_queries() -> list[dict[Any, Any]]:
    base = {
        **_base_query(),
        _const("return_data"): True,
        _const("match_limit"): _const("match_one"),
    }
    queries = [dict(base)]
    if icloud_keychain_available() and _const("sync_any") is not None:
        extra = dict(base)
        extra[_const("synchronizable")] = _const("sync_any")
        queries.append(extra)
    return queries


def _delete_queries() -> list[dict[Any, Any]]:
    queries = [_base_query()]
    if icloud_keychain_available() and _const("sync_any") is not None:
        extra = _base_query()
        extra[_const("synchronizable")] = _const("sync_any")
        queries.append(extra)
    return queries


def _add(attrs: dict[Any, Any]) -> tuple[int, Any]:
    from Security import SecItemAdd  # type: ignore[import-not-found]

    return _call_out(SecItemAdd, attrs)


def _copy(query: dict[Any, Any]) -> tuple[int, Any]:
    from Security import SecItemCopyMatching  # type: ignore[import-not-found]

    return _call_out(SecItemCopyMatching, query)


def _delete(query: dict[Any, Any]) -> int:
    from Security import SecItemDelete  # type: ignore[import-not-found]

    status = SecItemDelete(query)
    if isinstance(status, tuple):
        status = status[0]
    return int(status)


def _call_out(fn: Any, attrs: dict[Any, Any]) -> tuple[int, Any]:
    result = fn(attrs, None)
    if isinstance(result, tuple) and len(result) >= 2:
        return int(result[0]), result[1]
    return int(result), None


def _decode_secret(data: Any) -> str | None:
    if data is None:
        return None
    if isinstance(data, str):
        return data if data.strip() else None
    if isinstance(data, (bytes, bytearray, memoryview)):
        text = bytes(data).decode("utf-8")
        return text if text.strip() else None
    raw = getattr(data, "bytes", None)
    if callable(raw):
        try:
            text = bytes(raw()).decode("utf-8")
            return text if text.strip() else None
        except (TypeError, ValueError):
            pass
    try:
        text = bytes(data).decode("utf-8")
    except (TypeError, ValueError):
        return None
    return text if text.strip() else None


def _status_message(action: str, status: int) -> str:
    if status == -128:
        return "Keychain asked for permission, and it was declined."
    if status in {-25291, -25299, -25308}:
        return "This Mac’s Keychain is locked. Unlock it, then try again."
    if status == _ERR_MISSING_ENTITLEMENT:
        return (
            "iCloud Keychain isn’t available in this run. "
            "The key can still be saved on this Mac."
        )
    return f"Could not {action} the key in Keychain ({status})."


def _const(name: str) -> Any:
    if _consts is None:
        _load_security()
    assert _consts is not None
    return _consts[name]


def _load_security() -> None:
    global _consts
    if _consts is not None:
        return
    from Security import (  # type: ignore[import-not-found]
        errSecItemNotFound,
        kSecAttrAccessible,
        kSecAttrAccessibleAfterFirstUnlock,
        kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        kSecAttrAccount,
        kSecAttrLabel,
        kSecAttrService,
        kSecClass,
        kSecClassGenericPassword,
        kSecMatchLimit,
        kSecMatchLimitOne,
        kSecReturnData,
        kSecValueData,
    )

    module = __import__("Security")
    _consts = {
        "class": kSecClass,
        "generic": kSecClassGenericPassword,
        "service": kSecAttrService,
        "account": kSecAttrAccount,
        "label": kSecAttrLabel,
        "value": kSecValueData,
        "return_data": kSecReturnData,
        "match_limit": kSecMatchLimit,
        "match_one": kSecMatchLimitOne,
        "accessible": kSecAttrAccessible,
        "after_unlock": kSecAttrAccessibleAfterFirstUnlock,
        "this_device": kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        "synchronizable": getattr(module, "kSecAttrSynchronizable", None),
        "sync_any": getattr(module, "kSecAttrSynchronizableAny", None),
        "not_found": int(errSecItemNotFound),
    }
