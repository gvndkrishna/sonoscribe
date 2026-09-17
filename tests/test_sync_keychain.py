from sonoscribe.sync.keychain import (
    MemoryKeychain,
    SecurityKeychain,
    get_lock_secret,
    get_private_key,
    set_lock_secret,
    set_private_key,
    use_memory_keychain,
)


def test_memory_keychain_roundtrip() -> None:
    store = use_memory_keychain(MemoryKeychain())
    set_private_key("-----BEGIN PRIVATE KEY-----\nabc\n", "icloud")
    assert "BEGIN PRIVATE KEY" in (get_private_key() or "")
    assert store.scope == "icloud"
    set_private_key("-----BEGIN PRIVATE KEY-----\nabc\n", "local")
    assert store.scope == "local"


def test_memory_lock_secret_roundtrip() -> None:
    store = use_memory_keychain(MemoryKeychain())
    set_lock_secret("pbkdf2:sha256:1:ab:cd")
    assert get_lock_secret() == "pbkdf2:sha256:1:ab:cd"
    assert store.lock_blob.startswith("pbkdf2")


def test_security_delete_ignores_missing_entitlement(monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.sync.keychain._delete", lambda _query: -34018)
    monkeypatch.setattr(
        "sonoscribe.sync.keychain._const",
        lambda name: {"not_found": -25300}.get(name, name),
    )
    monkeypatch.setattr(
        "sonoscribe.sync.keychain._delete_queries",
        lambda: [{"probe": True}],
    )
    SecurityKeychain().delete()
