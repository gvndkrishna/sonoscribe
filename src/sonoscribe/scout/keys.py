"""Keychain storage for scout provider keys. Never returned to the dashboard."""

from __future__ import annotations

from sonoscribe.sync.keychain import (
    KeychainError,
    delete_scout_key as _delete,
    get_scout_key as _get,
    has_scout_key as _has,
    set_scout_key as _set,
)

_PROVIDERS = frozenset({"openai", "anthropic", "grok", "kimi", "bedrock", "local"})
__all__ = ["KeychainError", "delete_scout_key", "get_scout_key", "has_scout_key", "set_scout_key"]


def get_scout_key(provider: str) -> str | None:
    return _get(_account(provider))


def set_scout_key(provider: str, secret: str) -> None:
    text = str(secret or "").strip()
    if not text:
        raise KeychainError("Key is empty.")
    _set(_account(provider), text)


def delete_scout_key(provider: str) -> None:
    _delete(_account(provider))


def has_scout_key(provider: str) -> bool:
    return _has(_account(provider))


def _account(provider: str) -> str:
    name = str(provider or "").strip()
    if name not in _PROVIDERS:
        raise KeychainError("Unknown scout provider.")
    return name
