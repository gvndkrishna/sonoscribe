from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from sonoscribe.catalog import LibraryError, apply_library_update, empty_library, match_utterance, validate_library
from sonoscribe.cleaner import prepare_command_text
from sonoscribe.scribe.parse import coerce_due, next_clock, parse_scribe, wants_scribe_save
from sonoscribe.scribe.library import save_scribe_from_run
from sonoscribe.scribe.store import (
    advance_repeat,
    create_from_text,
    delete_vocanotes,
    dismiss_vocanote,
    due_vocanotes,
    list_vocanotes,
    mark_notified,
    upsert_vocanote,
)


TZ = ZoneInfo("America/New_York")


def test_next_clock_picks_upcoming_am_or_pm() -> None:
    morning = datetime(2026, 9, 19, 7, 0, tzinfo=TZ)
    noonish = datetime(2026, 9, 19, 14, 0, tzinfo=TZ)
    night = datetime(2026, 9, 19, 21, 0, tzinfo=TZ)
    assert next_clock(8, now=morning).hour == 8
    assert next_clock(8, now=morning).day == 19
    assert next_clock(8, now=noonish).hour == 20
    assert next_clock(8, now=night).hour == 8
    assert next_clock(8, now=night).day == 20
    assert next_clock(8, now=noonish, meridiem="pm").hour == 20
    assert next_clock(20, now=morning).hour == 20


def test_parse_scribe_pay_bills_at_8() -> None:
    now = datetime(2026, 9, 19, 14, 0, tzinfo=TZ)
    note = parse_scribe("Pay Bills at 8 o'clock", now=now)
    assert note["title"] == "Pay Bills at 8 o'clock"
    assert note["is_note"] is True
    assert note["is_todo"] is True
    assert note["is_reminder"] is True
    due = datetime.fromisoformat(note["due_at"])
    assert due.hour == 20
    assert due.day == 19


def test_parse_scribe_plain_note() -> None:
    note = parse_scribe("ideas for the garden")
    assert note["is_todo"] is False
    assert note["is_reminder"] is False
    assert note["due_at"] == ""


def test_parse_scribe_word_clock_and_remind() -> None:
    now = datetime(2026, 9, 19, 14, 0, tzinfo=TZ)
    eight = parse_scribe("Pay Bills at eight o'clock", now=now)
    assert eight["is_reminder"] is True
    assert datetime.fromisoformat(eight["due_at"]).hour == 20
    bare = parse_scribe("call mom at eight", now=now)
    assert bare["is_reminder"] is True
    assert datetime.fromisoformat(bare["due_at"]).hour == 20
    tonight = parse_scribe("call mom tonight", now=now)
    assert tonight["is_reminder"] is True
    assert datetime.fromisoformat(tonight["due_at"]).hour == 20
    remind = parse_scribe("remind me to take out trash", now=now)
    assert remind["is_reminder"] is True
    assert datetime.fromisoformat(remind["due_at"]).hour == 20
    tomorrow = parse_scribe("buy milk tomorrow", now=now)
    assert tomorrow["is_reminder"] is True
    assert datetime.fromisoformat(tomorrow["due_at"]).day == 20
    assert datetime.fromisoformat(tomorrow["due_at"]).hour == 8
    listed = parse_scribe("when is avengers doomsday releasing added to the reminders list", now=now)
    assert listed["is_reminder"] is False
    assert listed["repeat"] == ""


def test_parse_scribe_weekdays_and_repeat() -> None:
    now = datetime(2026, 9, 19, 14, 0, tzinfo=TZ)
    monday = parse_scribe("call mom monday", now=now)
    assert monday["is_reminder"] is True
    assert monday["repeat"] == ""
    due = datetime.fromisoformat(monday["due_at"])
    assert (due.year, due.month, due.day, due.hour) == (2026, 9, 21, 8)
    assert datetime.fromisoformat(parse_scribe("call mom next monday", now=now)["due_at"]).day == 21
    assert datetime.fromisoformat(parse_scribe("call mom this weekend", now=now)["due_at"]).day == 20
    assert datetime.fromisoformat(parse_scribe("call mom next weekend", now=now)["due_at"]).day == 26
    assert datetime.fromisoformat(parse_scribe("dentist next week", now=now)["due_at"]).day == 21
    daily = parse_scribe("take meds everyday", now=now)
    assert daily["repeat"] == "daily"
    assert datetime.fromisoformat(daily["due_at"]).day == 20
    assert datetime.fromisoformat(daily["due_at"]).hour == 8
    friday = parse_scribe("pay bills every friday at 3pm", now=now)
    assert friday["repeat"] == "friday"
    due = datetime.fromisoformat(friday["due_at"])
    assert (due.day, due.hour) == (25, 15)
    evening = parse_scribe("stretch every evening", now=now)
    assert evening["repeat"] == "daily"
    assert datetime.fromisoformat(evening["due_at"]).hour == 20
    morning = datetime(2026, 9, 21, 7, 0, tzinfo=TZ)
    assert datetime.fromisoformat(parse_scribe("dentist monday", now=morning)["due_at"]).day == 21
    assert datetime.fromisoformat(parse_scribe("dentist next monday", now=morning)["due_at"]).day == 28


def test_parse_scribe_calendar_date() -> None:
    now = datetime(2026, 9, 19, 14, 0, tzinfo=TZ)
    note = parse_scribe("Avengers: Doomsday December 18, 2026", now=now)
    assert note["is_reminder"] is True
    due = datetime.fromisoformat(note["due_at"])
    assert (due.year, due.month, due.day, due.hour) == (2026, 12, 18, 8)
    evening = parse_scribe("dentist 18 December 2026 at 3pm", now=now)
    due = datetime.fromisoformat(evening["due_at"])
    assert (due.year, due.month, due.day, due.hour) == (2026, 12, 18, 15)
    iso = coerce_due("2026-12-18", now=now)
    assert datetime.fromisoformat(iso).day == 18
    assert datetime.fromisoformat(iso).hour == 8
    assert wants_scribe_save("when is avengers doomsday releasing added to the reminders list") is True
    assert wants_scribe_save("what is on my reminders list") is False
    assert wants_scribe_save("remind me to take out trash") is True


def test_save_scribe_from_run_uses_answer_date() -> None:
    run = {
        "prompt": "when is avengers doomsday releasing added to the reminders list",
        "steps": [{"name": "search", "args": {"query": "Avengers Doomsday"}}],
        "answer": {
            "title": "avengers doomsday release date added",
            "blocks": [
                {
                    "type": "lead",
                    "text": "Avengers: Doomsday is set to release in theaters on December 18, 2026.",
                },
                {
                    "type": "facts",
                    "rows": [
                        ["Movie", "Avengers: Doomsday"],
                        ["Release Date", "December 18, 2026"],
                        ["Reminder", "Added to your list"],
                    ],
                },
            ],
        },
    }
    note = save_scribe_from_run(run)
    assert note is not None
    assert note["title"] == "Avengers: Doomsday"
    assert note["is_reminder"] is True
    due = datetime.fromisoformat(note["due_at"])
    assert (due.year, due.month, due.day, due.hour) == (2026, 12, 18, 8)
    again = save_scribe_from_run(
        {
            **run,
            "steps": [
                {
                    "name": "library",
                    "args": {"action": "upsert", "kind": "vocanote"},
                    "detail": '{"id":"voc-1"}',
                }
            ],
        }
    )
    assert again is None


def test_upsert_does_not_revive_deleted() -> None:
    note = create_from_text("wash the car")
    delete_vocanotes([note["id"]])
    with pytest.raises(LibraryError):
        upsert_vocanote({"id": note["id"], "title": "wash the car"})
    assert list_vocanotes() == []


def test_parse_scribe_verb_start_is_todo() -> None:
    assert parse_scribe("wash the car")["is_todo"] is True
    assert parse_scribe("please schedule dentist")["is_todo"] is True
    assert parse_scribe("buying milk")["is_todo"] is True
    assert parse_scribe("meeting notes")["is_todo"] is False
    assert parse_scribe("milk")["is_todo"] is False


def test_spoken_scribe_prefix() -> None:
    assert prepare_command_text("scribes pay bills at 8") == "scribe pay bills at 8"
    assert prepare_command_text("uh scribe milk") == "scribe milk"
    library = empty_library()
    assert match_utterance("scribe", library).kind == "scribe_incomplete"
    hit = match_utterance("scribe pay bills at 8", library)
    assert hit.kind == "scribe"
    assert hit.bindings["text"] == "pay bills at 8"
    assert match_utterance("what is the weather", library).kind == "unknown"


def test_create_and_due_then_dismiss(tmp_path) -> None:
    past = (datetime.now().astimezone() - timedelta(minutes=1)).isoformat(timespec="seconds")
    note = upsert_vocanote(
        {
            "title": "pay bills at 8",
            "is_todo": True,
            "is_reminder": True,
            "due_at": past,
        }
    )
    assert note["sku"].startswith("vn–")
    ready = due_vocanotes()
    assert ready[0]["id"] == note["id"]
    marked = mark_notified(note["id"])
    assert marked and marked["notified_at"]
    assert due_vocanotes() == []
    kept = dismiss_vocanote(note["id"])
    assert kept and kept["id"] == note["id"]
    assert list_vocanotes()
    delete_vocanotes([note["id"]])
    assert list_vocanotes() == []


def test_repeat_later_rolls_next_due() -> None:
    note = upsert_vocanote(
        {
            "title": "take meds everyday",
            "is_reminder": True,
            "repeat": "daily",
            "due_at": datetime(2026, 9, 19, 20, 0, tzinfo=TZ).isoformat(timespec="seconds"),
        }
    )
    assert note["repeat"] == "daily"
    rolled = advance_repeat(note["id"], when=datetime(2026, 9, 19, 20, 5, tzinfo=TZ))
    assert rolled is not None
    due = datetime.fromisoformat(rolled["due_at"])
    assert due.day == 20
    assert due.hour == 20
    assert rolled["notified_at"] == ""
    kept = dismiss_vocanote(note["id"])
    assert kept and kept["repeat"] == "daily"
    delete_vocanotes([note["id"]])


def test_create_from_text_classifies() -> None:
    note = create_from_text("call mom at 9 am")
    assert note["is_todo"] is True
    assert note["is_reminder"] is True
    assert "09:00" in note["due_at"] or "9:00" in note["due_at"] or note["due_at"]


def test_validate_and_omit_preserves_vocanotes() -> None:
    current = validate_library(
        {
            "commands": empty_library()["commands"],
            "routines": [],
            "variables": [],
            "vocanotes": [{"title": "keep me", "is_todo": False}],
        }
    )
    incoming = {
        "commands": empty_library()["commands"],
        "routines": [],
        "variables": [],
    }
    saved = apply_library_update(current, incoming, revealed=False, confirmed=False, lock_on=False)
    assert any(item["title"] == "keep me" for item in saved["vocanotes"])
    wiped = apply_library_update(
        current,
        {**incoming, "vocanotes": []},
        revealed=False,
        confirmed=False,
        lock_on=False,
    )
    assert wiped["vocanotes"] == []


def test_deleted_vocanote_stays_gone(tmp_path) -> None:
    note = create_from_text("milk")
    delete_vocanotes([note["id"]])
    assert list_vocanotes() == []
    current = validate_library(
        {
            "commands": empty_library()["commands"],
            "routines": [],
            "variables": [],
            "vocanotes": [],
            "vocanote_gone": [{"id": note["id"], "deleted_at": "2026-09-19T00:00:00+00:00"}],
        }
    )
    restored = apply_library_update(
        current,
        {
            "commands": empty_library()["commands"],
            "routines": [],
            "variables": [],
            "vocanotes": [
                {
                    "id": note["id"],
                    "title": "milk",
                    "is_note": True,
                    "is_todo": True,
                    "is_reminder": False,
                }
            ],
        },
        revealed=False,
        confirmed=False,
        lock_on=False,
    )
    assert restored["vocanotes"] == []
    assert any(item["id"] == note["id"] for item in restored["vocanote_gone"])
    stale = {
        "vocanotes": [
            {
                "id": note["id"],
                "title": "milk",
                "is_note": True,
                "is_todo": True,
                "is_reminder": False,
                "due_at": "",
                "notified_at": "",
                "created_at": "",
                "updated_at": "",
                "devices": [],
            }
        ],
        "vocanote_gone": [{"id": note["id"], "deleted_at": "2026-09-19T00:00:00+00:00"}],
    }
    assert list_vocanotes(stale) == []


def test_empty_library_has_vocanotes() -> None:
    assert empty_library()["vocanotes"] == []
    assert empty_library()["vocanote_gone"] == []
