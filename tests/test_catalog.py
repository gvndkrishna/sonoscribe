import json

import pytest

from sonoscribe.catalog import (
    LibraryError,
    commands_from_github_map,
    empty_library,
    load_library,
    match_utterance,
    normalize_phrase,
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


def test_load_creates_seed_when_missing(tmp_path, monkeypatch) -> None:
    library_file = tmp_path / "nested" / "library.json"
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(library_file))
    monkeypatch.setenv("SONOSCRIBE_ROUTINES", str(tmp_path / "missing-routines.json"))
    library = load_library()
    ids = {item["id"] for item in library["commands"]}
    assert "kbd-enter" in ids
    assert "web-android" in ids
    assert library["routines"] == []
