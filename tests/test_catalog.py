import json

import pytest

from pathlib import Path

from sonoscribe.catalog import (
    LibraryError,
    clear_library_cache,
    command_by_id,
    commands_from_github_map,
    empty_library,
    load_library,
    match_utterance,
    normalize_phrase,
    remap_device_id,
    save_library,
    validate_library,
)


def test_normalize_phrase_strips_punctuation() -> None:
    assert normalize_phrase("GitHub Android.") == "github android"
    assert normalize_phrase("  enter  ") == "enter"


def test_enter_and_aliases_match_seed() -> None:
    library = empty_library()
    assert match_utterance("enter", library).command["id"] == "kbd-enter"
    assert match_utterance("scratch that", library).command["id"] == "kbd-scratch"
    assert match_utterance("delete the last word", library).command["id"] == "kbd-delete-word"


def test_website_aliases_match_android() -> None:
    library = empty_library()
    for phrase in ("android", "github android", "git hub android", "GitHub Android."):
        hit = match_utterance(phrase, library)
        assert hit.kind == "command"
        assert hit.command["type"] == "website"
        assert "sqx-core-android" in hit.command["url"]


def test_fluent_enter_is_unknown() -> None:
    assert match_utterance("you may enter", empty_library()).kind == "unknown"


def test_routine_prefix() -> None:
    library = validate_library(
        {
            "commands": empty_library()["commands"],
            "routines": [
                {
                    "id": "rtn-work",
                    "name": "work",
                    "phrases": ["office"],
                    "steps": [{"command_id": "kbd-enter", "delay_ms": 0}],
                }
            ],
        }
    )
    assert match_utterance("routine", library).kind == "routine_incomplete"
    work = match_utterance("routine work", library)
    assert work.kind == "routine"
    assert work.routine["id"] == "rtn-work"
    office = match_utterance("routine office", library)
    assert office.kind == "routine"
    assert match_utterance("routine missing", library).kind == "unknown"
    assert match_utterance("enter", library).kind == "command"


def test_phrase_cannot_start_with_routine() -> None:
    with pytest.raises(LibraryError):
        validate_library(
            {
                "commands": [
                    {
                        "id": "bad",
                        "type": "keyboard",
                        "name": "Bad",
                        "phrases": ["routine boom"],
                        "action": "enter",
                    }
                ],
                "routines": [],
            }
        )


def test_duplicate_phrases_rejected() -> None:
    with pytest.raises(LibraryError):
        validate_library(
            {
                "commands": [
                    {
                        "id": "a",
                        "type": "keyboard",
                        "name": "A",
                        "phrases": ["enter"],
                        "action": "enter",
                    },
                    {
                        "id": "b",
                        "type": "keyboard",
                        "name": "B",
                        "phrases": ["enter"],
                        "action": "backspace",
                    },
                ],
                "routines": [],
            }
        )


def test_website_url_must_be_http() -> None:
    with pytest.raises(LibraryError):
        validate_library(
            {
                "commands": [
                    {
                        "id": "w",
                        "type": "website",
                        "name": "Nope",
                        "phrases": ["nope"],
                        "url": "javascript:alert(1)",
                    }
                ],
                "routines": [],
            }
        )


def test_github_map_becomes_website_commands() -> None:
    commands = commands_from_github_map(
        {"android": "https://github.com/SquareX-Backup/sqx-core-android"}
    )
    assert commands[0]["id"] == "web-android"
    assert "git hub android" in commands[0]["phrases"]


def test_load_migrates_legacy_routines_json(tmp_path, monkeypatch) -> None:
    legacy = tmp_path / "routines.json"
    legacy.write_text(
        json.dumps(
            {"github": {"android": "https://github.com/SquareX-Backup/sqx-core-android"}}
        )
    )
    library_file = tmp_path / "library.json"
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(library_file))
    monkeypatch.setenv("SONOSCRIBE_ROUTINES", str(legacy))
    library = load_library()
    android = next(item for item in library["commands"] if item["id"] == "web-android")
    assert android["type"] == "website"
    assert "github android" in android["phrases"]
    assert library_file.exists()
    assert json.loads(legacy.read_text())["github"]["android"]


def test_app_command_accepts_bundle_id_only() -> None:
    library = validate_library(
        {
            "commands": [
                {
                    "id": "app-safari",
                    "type": "app",
                    "name": "Safari",
                    "phrases": ["safari"],
                    "bundle_id": "com.apple.Safari",
                }
            ],
            "routines": [],
        }
    )
    assert library["commands"][0]["bundle_id"] == "com.apple.Safari"
    assert "app" not in library["commands"][0]


def test_app_command_keeps_display_name() -> None:
    library = validate_library(
        {
            "commands": [
                {
                    "id": "app-safari",
                    "type": "app",
                    "name": "Open Safari",
                    "phrases": ["safari"],
                    "bundle_id": "com.apple.Safari",
                    "app": "Safari",
                }
            ],
            "routines": [],
        }
    )
    command = library["commands"][0]
    assert command["bundle_id"] == "com.apple.Safari"
    assert command["app"] == "Safari"


def test_app_command_detects_bundle_id_in_app_field() -> None:
    library = validate_library(
        {
            "commands": [
                {
                    "id": "app-notes",
                    "type": "app",
                    "name": "Notes",
                    "phrases": ["notes"],
                    "app": "com.apple.Notes",
                }
            ],
            "routines": [],
        }
    )
    assert library["commands"][0]["bundle_id"] == "com.apple.Notes"
    assert "app" not in library["commands"][0]


def test_keyboard_accepts_recorded_keys() -> None:
    library = validate_library(
        {
            "commands": [
                {
                    "id": "kbd-save",
                    "type": "keyboard",
                    "name": "Save",
                    "phrases": ["save"],
                    "keys": [{"vk": 1, "mods": ["command"], "label": "⌘S"}],
                }
            ],
            "routines": [],
        }
    )
    assert library["commands"][0]["keys"][0]["vk"] == 1


def test_keyboard_requires_keys_or_action() -> None:
    with pytest.raises(LibraryError):
        validate_library(
            {
                "commands": [
                    {
                        "id": "kbd-empty",
                        "type": "keyboard",
                        "name": "Empty",
                        "phrases": ["empty keys"],
                    }
                ],
                "routines": [],
            }
        )


def test_script_command_requires_body_or_path() -> None:
    with pytest.raises(LibraryError):
        validate_library(
            {
                "commands": [
                    {
                        "id": "scr-empty",
                        "type": "script",
                        "name": "Empty",
                        "phrases": ["run empty"],
                        "runtime": "bash",
                    }
                ],
                "routines": [],
            }
        )


def test_script_command_accepts_pasted_bash() -> None:
    library = validate_library(
        {
            "commands": [
                {
                    "id": "scr-hi",
                    "type": "script",
                    "name": "Hi",
                    "phrases": ["run hi"],
                    "runtime": "bash",
                    "body": "echo hi",
                }
            ],
            "routines": [],
        }
    )
    assert library["commands"][0]["body"] == "echo hi"


def test_app_command_requires_name_or_bundle_id() -> None:
    with pytest.raises(LibraryError):
        validate_library(
            {
                "commands": [
                    {
                        "id": "app-empty",
                        "type": "app",
                        "name": "Empty",
                        "phrases": ["empty"],
                    }
                ],
                "routines": [],
            }
        )


def test_load_creates_seed_when_missing(tmp_path, monkeypatch) -> None:
    library_file = tmp_path / "nested" / "library.json"
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(library_file))
    monkeypatch.setenv("SONOSCRIBE_ROUTINES", str(tmp_path / "missing-routines.json"))
    library = load_library()
    ids = {item["id"] for item in library["commands"]}
    assert "kbd-enter" in ids
    assert "web-android" in ids
    assert library["routines"] == []


def test_command_by_id_uses_index() -> None:
    library = empty_library()
    assert command_by_id(library, "kbd-enter")["action"] == "enter"
    assert command_by_id(library, "missing") is None


def test_load_library_reuses_memory_when_file_unchanged(tmp_path, monkeypatch) -> None:
    clear_library_cache()
    library_file = tmp_path / "library.json"
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(library_file))
    monkeypatch.setenv("SONOSCRIBE_ROUTINES", str(tmp_path / "no-legacy.json"))
    first = load_library()
    reads = {"n": 0}
    original = Path.read_text

    def counting(self: Path, *args: object, **kwargs: object) -> str:
        if self.resolve() == library_file.resolve():
            reads["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)
    second = load_library()
    assert second is first
    assert reads["n"] == 0
    assert match_utterance("enter", second).command["id"] == "kbd-enter"


def test_load_library_reloads_when_file_changes(tmp_path, monkeypatch) -> None:
    clear_library_cache()
    library_file = tmp_path / "library.json"
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(library_file))
    monkeypatch.setenv("SONOSCRIBE_ROUTINES", str(tmp_path / "no-legacy.json"))
    first = load_library()
    assert command_by_id(first, "kbd-enter") is not None
    library_file.write_text(
        json.dumps(
            {
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
        )
        + "\n",
        encoding="utf-8",
    )
    second = load_library()
    assert second is not first
    assert [item["id"] for item in second["commands"]] == ["kbd-only"]
    assert match_utterance("only", second).command["id"] == "kbd-only"
    assert match_utterance("enter", second).kind == "unknown"


def test_save_library_updates_cache(tmp_path, monkeypatch) -> None:
    clear_library_cache()
    library_file = tmp_path / "library.json"
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(library_file))
    monkeypatch.setenv("SONOSCRIBE_ROUTINES", str(tmp_path / "no-legacy.json"))
    load_library()
    saved = save_library(
        {
            "commands": [
                {
                    "id": "sys-lock",
                    "type": "system",
                    "name": "Lock",
                    "phrases": ["lock screen"],
                    "action": "lock",
                }
            ],
            "routines": [],
        }
    )
    assert load_library() is saved
    assert match_utterance("lock screen", saved).command["id"] == "sys-lock"


def test_match_skips_commands_for_other_devices() -> None:
    library = validate_library(
        {
            "commands": [
                {
                    "id": "kbd-here",
                    "type": "keyboard",
                    "name": "Here",
                    "phrases": ["only here"],
                    "action": "enter",
                    "devices": ["dev-a"],
                },
                {
                    "id": "kbd-there",
                    "type": "keyboard",
                    "name": "There",
                    "phrases": ["only there"],
                    "action": "enter",
                    "devices": ["dev-b"],
                },
                {
                    "id": "kbd-all",
                    "type": "keyboard",
                    "name": "All",
                    "phrases": ["everywhere"],
                    "action": "enter",
                    "devices": [],
                },
            ],
            "routines": [],
        }
    )
    assert match_utterance("only here", library, "dev-a").command["id"] == "kbd-here"
    assert match_utterance("only there", library, "dev-a").kind == "unknown"
    assert match_utterance("everywhere", library, "dev-a").command["id"] == "kbd-all"


def _scoped(cmd_id: str, name: str, phrase: str, apps: list[dict[str, str]]) -> dict:
    return {
        "id": cmd_id,
        "type": "keyboard",
        "name": name,
        "phrases": [phrase],
        "action": "enter",
        "apps": apps,
    }


def test_duplicate_phrases_ok_in_different_apps() -> None:
    library = validate_library(
        {
            "commands": [
                _scoped("kbd-safari", "Safari save", "save", [{"bundle_id": "com.apple.Safari", "name": "Safari"}]),
                _scoped("kbd-chrome", "Chrome save", "save", [{"bundle_id": "com.google.Chrome", "name": "Chrome"}]),
            ],
            "routines": [],
        }
    )
    safari = {"bundle_id": "com.apple.Safari", "name": "Safari"}
    chrome = {"bundle_id": "com.google.Chrome", "name": "Chrome"}
    assert match_utterance("save", library, "", safari).command["id"] == "kbd-safari"
    assert match_utterance("save", library, "", chrome).command["id"] == "kbd-chrome"


def test_overlapping_app_phrases_rejected() -> None:
    with pytest.raises(LibraryError, match="save"):
        validate_library(
            {
                "commands": [
                    _scoped("kbd-safari", "Safari save", "save", [{"bundle_id": "com.apple.Safari", "name": "Safari"}]),
                    _scoped(
                        "kbd-both",
                        "Both save",
                        "save",
                        [
                            {"bundle_id": "com.apple.Safari", "name": "Safari"},
                            {"bundle_id": "com.google.Chrome", "name": "Chrome"},
                        ],
                    ),
                ],
                "routines": [],
            }
        )


def test_global_and_scoped_may_share_phrase() -> None:
    library = validate_library(
        {
            "commands": [
                {
                    "id": "kbd-global",
                    "type": "keyboard",
                    "name": "Global save",
                    "phrases": ["save"],
                    "action": "enter",
                },
                _scoped("kbd-safari", "Safari save", "save", [{"bundle_id": "com.apple.Safari", "name": "Safari"}]),
            ],
            "routines": [],
        }
    )
    safari = {"bundle_id": "com.apple.Safari", "name": "Safari"}
    notes = {"bundle_id": "com.apple.Notes", "name": "Notes"}
    assert match_utterance("save", library, "", safari).command["id"] == "kbd-safari"
    assert match_utterance("save", library, "", notes).command["id"] == "kbd-global"
    assert match_utterance("save", library, "").command["id"] == "kbd-global"


def test_scoped_command_unknown_in_other_app() -> None:
    library = validate_library(
        {
            "commands": [
                _scoped("kbd-safari", "Safari save", "export", [{"bundle_id": "com.apple.Safari", "name": "Safari"}]),
            ],
            "routines": [],
        }
    )
    notes = {"bundle_id": "com.apple.Notes", "name": "Notes"}
    assert match_utterance("export", library, "", notes).kind == "unknown"
    assert match_utterance("export", library, "", {"bundle_id": "com.apple.Safari", "name": "Safari"}).command["id"] == "kbd-safari"


def test_missing_frontmost_uses_lone_scoped_command() -> None:
    library = validate_library(
        {
            "commands": [
                _scoped("kbd-safari", "Safari save", "export", [{"bundle_id": "com.apple.Safari", "name": "Safari"}]),
            ],
            "routines": [],
        }
    )
    assert match_utterance("export", library, "", None).command["id"] == "kbd-safari"


def test_missing_frontmost_unknown_when_two_scoped() -> None:
    library = validate_library(
        {
            "commands": [
                _scoped("kbd-safari", "Safari save", "save", [{"bundle_id": "com.apple.Safari", "name": "Safari"}]),
                _scoped("kbd-chrome", "Chrome save", "save", [{"bundle_id": "com.google.Chrome", "name": "Chrome"}]),
            ],
            "routines": [],
        }
    )
    assert match_utterance("save", library, "", None).kind == "unknown"


def test_app_scope_still_respects_devices() -> None:
    library = validate_library(
        {
            "commands": [
                {
                    "id": "kbd-here",
                    "type": "keyboard",
                    "name": "Here",
                    "phrases": ["save"],
                    "action": "enter",
                    "devices": ["dev-a"],
                    "apps": [{"bundle_id": "com.apple.Safari", "name": "Safari"}],
                }
            ],
            "routines": [],
        }
    )
    safari = {"bundle_id": "com.apple.Safari", "name": "Safari"}
    assert match_utterance("save", library, "dev-a", safari).command["id"] == "kbd-here"
    assert match_utterance("save", library, "dev-b", safari).kind == "unknown"


def test_remap_device_id_rewrites_assignments() -> None:
    save_library(
        {
            "commands": [
                {
                    "type": "keyboard",
                    "name": "Here",
                    "phrases": ["only here"],
                    "action": "enter",
                    "devices": ["dev-old"],
                }
            ],
            "routines": [],
        }
    )
    assert remap_device_id("dev-old", "C02SERIAL01") is True
    here = next(item for item in load_library()["commands"] if item["name"] == "Here")
    assert here["devices"] == ["C02SERIAL01"]


def test_empty_library_has_variables() -> None:
    library = empty_library()
    assert library["variables"] == []


def test_phrase_cannot_start_with_slot() -> None:
    with pytest.raises(LibraryError):
        validate_library(
            {
                "commands": [
                    {
                        "id": "bad",
                        "type": "app",
                        "name": "Bad",
                        "phrases": ["{1} open"],
                        "app": "{1}",
                    }
                ]
            }
        )


def test_unknown_variable_rejected() -> None:
    with pytest.raises(LibraryError):
        validate_library(
            {
                "commands": [
                    {
                        "id": "txt-insert",
                        "type": "text",
                        "name": "Insert",
                        "phrases": ["insert {hello}"],
                        "text": "{hello}",
                    }
                ]
            }
        )


def test_exact_phrase_beats_slot() -> None:
    library = validate_library(
        {
            "commands": [
                {
                    "id": "app-safari",
                    "type": "app",
                    "name": "Safari",
                    "phrases": ["open safari"],
                    "app": "Safari",
                },
                {
                    "id": "app-any",
                    "type": "app",
                    "name": "Open",
                    "phrases": ["open {1}"],
                    "app": "{1}",
                },
            ]
        }
    )
    safari = match_utterance("open safari", library)
    assert safari.command["id"] == "app-safari"
    other = match_utterance("open notes", library)
    assert other.command["id"] == "app-any"
    assert other.bindings["1"] == "notes"


def test_named_variable_text_command() -> None:
    library = validate_library(
        {
            "variables": [{"id": "var-hello", "name": "hello", "value": "Greetings guys"}],
            "commands": [
                {
                    "id": "txt-insert",
                    "type": "text",
                    "name": "Insert hello",
                    "phrases": ["insert {hello}"],
                    "text": "{hello}",
                }
            ],
        }
    )
    hit = match_utterance("insert hello", library)
    assert hit.kind == "command"
    assert hit.command["id"] == "txt-insert"
    assert hit.bindings["hello"] == "Greetings guys"


def test_secrets_only_match_when_lock_is_on() -> None:
    from sonoscribe.catalog import usable_library

    library = validate_library(
        {
            "variables": [
                {"id": "var-hello", "name": "hello", "value": "Greetings guys"},
                {"id": "var-hush", "name": "hush", "value": "quiet", "secret": True},
            ],
            "commands": [
                {
                    "id": "txt-hello",
                    "type": "text",
                    "name": "Insert hello",
                    "phrases": ["insert {hello}"],
                    "text": "{hello}",
                },
                {
                    "id": "txt-hush",
                    "type": "text",
                    "name": "Insert hush",
                    "phrases": ["insert {hush}"],
                    "text": "{hush}",
                    "secret": True,
                },
                {
                    "id": "kbd-secret",
                    "type": "keyboard",
                    "name": "Secret enter",
                    "phrases": ["secret enter please"],
                    "action": "enter",
                    "secret": True,
                },
            ],
        }
    )
    locked = usable_library(library, lock_on=True)
    assert match_utterance("secret enter please", locked).command["id"] == "kbd-secret"
    hush = match_utterance("insert hush", locked)
    assert hush.command["id"] == "txt-hush"
    assert hush.bindings["hush"] == "quiet"
    open_lib = usable_library(library, lock_on=False)
    assert match_utterance("secret enter please", open_lib).kind == "unknown"
    assert match_utterance("insert hush", open_lib).kind == "unknown"
    hello = match_utterance("insert hello", open_lib)
    assert hello.command["id"] == "txt-hello"


def test_routine_slot_bindings_pass_through() -> None:
    library = validate_library(
        {
            "commands": [
                {
                    "id": "txt-note",
                    "type": "text",
                    "name": "Note",
                    "phrases": ["note"],
                    "text": "{1}",
                }
            ],
            "routines": [
                {
                    "id": "rtn-send",
                    "name": "send {1}",
                    "phrases": [],
                    "steps": [{"command_id": "txt-note", "delay_ms": 0}],
                }
            ],
        }
    )
    hit = match_utterance("routine send report", library)
    assert hit.kind == "routine"
    assert hit.routine["id"] == "rtn-send"
    assert hit.bindings["1"] == "report"
