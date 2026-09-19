"""Spoken scout: LLM harness, tools, and local history."""

from sonoscribe.scout.harness import (
    ScoutBusy,
    ScoutConfigError,
    ScoutRunner,
    cancel_scout,
    confirm_scout,
    current_scout,
    delete_scouts,
    public_scout_state,
    rename_scout,
    request_insert,
    set_brief_insert,
    set_brief_notice,
    set_runner,
    set_scout_continue,
    spoken_confirm,
    start_scout,
    scout_continue_id,
    scout_history,
)
from sonoscribe.scout.keys import KeychainError, delete_scout_key, has_scout_key, set_scout_key
from sonoscribe.scout.providers import DEFAULT_MODELS, SCOUT_PROVIDERS
from sonoscribe.scout.store import clear_scout_cache

__all__ = [
    "DEFAULT_MODELS",
    "SCOUT_PROVIDERS",
    "KeychainError",
    "ScoutBusy",
    "ScoutConfigError",
    "ScoutRunner",
    "cancel_scout",
    "clear_scout_cache",
    "confirm_scout",
    "current_scout",
    "delete_scout_key",
    "delete_scouts",
    "has_scout_key",
    "public_scout_state",
    "rename_scout",
    "request_insert",
    "set_brief_insert",
    "set_brief_notice",
    "set_runner",
    "set_scout_continue",
    "set_scout_key",
    "spoken_confirm",
    "start_scout",
    "scout_continue_id",
    "scout_history",
]
