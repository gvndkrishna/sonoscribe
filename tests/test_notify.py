from sonoscribe.notify import (
    BUBBLE_SECONDS,
    SCRIPT_PREVIEW_MAX_CHARS,
    is_script_confirm,
    notice_blurb,
    notice_body,
    notice_cancel_label,
    notice_dismiss_label,
    notice_insert_label,
    notice_kicker,
    notice_later_label,
    notice_menu_label,
    notice_run_label,
    notice_script_body,
    notice_title,
    reminder_done_label,
    reminder_kicker,
    reminder_title,
    should_notice,
)


def test_notice_copy() -> None:
    run = {
        "id": "tsk-1",
        "status": "done",
        "title": "chicago weather",
        "sku": "sc–01",
        "answer": {"kind": "qa", "title": "chicago weather", "blurb": "52°", "blocks": []},
    }
    assert should_notice(run) is True
    assert BUBBLE_SECONDS == 5
    assert notice_kicker("done") == "scout"
    assert notice_kicker("error") == "error"
    assert notice_kicker("needs_confirm") == "confirm"
    assert notice_title(run) == "chicago weather"
    assert notice_blurb(run) == "52°"
    assert notice_body(run) == "52°"
    assert notice_menu_label(run) == "sc–01  chicago weather · 52°"
    assert notice_insert_label() == "insert"
    assert notice_dismiss_label() == "dismiss"
    assert notice_run_label() == "run"
    assert notice_cancel_label() == "cancel"
    assert notice_later_label() == "later"
    assert should_notice({"id": "tsk-1", "status": "cancelled"}) is False
    assert should_notice({"status": "done"}) is False
    assert notice_title({"prompt": "wind on the lake"}) == "wind on the lake"


def test_notice_blurb_falls_back_to_lead() -> None:
    run = {
        "id": "tsk-2",
        "status": "done",
        "title": "lake wind",
        "answer": {"kind": "qa", "title": "lake wind", "blocks": [{"type": "lead", "text": "12 mph from the west"}]},
    }
    assert notice_blurb(run) == "12 mph from the west"
    assert notice_menu_label(run) == "lake wind · 12 mph from the west"


def test_notice_blurb_keeps_a_few_words() -> None:
    run = {
        "id": "tsk-5",
        "status": "done",
        "title": "endgame tickets",
        "sku": "sc–01",
        "answer": {
            "kind": "qa",
            "title": "endgame tickets",
            "blurb": "tickets not on sale",
            "blocks": [{"type": "lead", "text": "BookMyShow has not opened booking yet."}],
        },
    }
    assert notice_blurb(run) == "tickets not on sale"
    assert "tickets not on sale" in notice_menu_label(run)


def test_notice_blurb_for_confirm_and_error() -> None:
    assert notice_blurb({"id": "tsk-3", "status": "needs_confirm", "confirm": {"title": "write file"}}) == "write file"
    assert notice_blurb({"id": "tsk-4", "status": "error", "error": "missing api key"}) == "missing api key"


def test_reminder_notice_is_title_only() -> None:
    assert reminder_kicker() == "scribe"
    assert reminder_done_label() == "done"
    assert reminder_title({"title": "pay bills at 8 o'clock"}) == "pay bills at 8 o'clock"
    assert reminder_title({}) == "reminder"


def test_script_confirm_preview_hides_when_huge() -> None:
    short = {
        "id": "tsk-script",
        "status": "needs_confirm",
        "confirm": {"tool": "run_script", "title": "run bash", "preview": "echo hello"},
    }
    huge = {
        "id": "tsk-huge",
        "status": "needs_confirm",
        "confirm": {
            "tool": "run_script",
            "title": "run bash",
            "preview": "echo " + ("x" * (SCRIPT_PREVIEW_MAX_CHARS + 10)),
        },
    }
    write = {
        "id": "tsk-write",
        "status": "needs_confirm",
        "confirm": {"tool": "write_file", "title": "write file", "preview": "notes.txt\n\nhello"},
    }
    assert is_script_confirm(short) is True
    assert notice_script_body(short) == "echo hello"
    assert is_script_confirm(huge) is True
    assert notice_script_body(huge) == ""
    assert is_script_confirm(write) is False
    assert notice_script_body(write) == ""
    tall = {
        "id": "tsk-tall",
        "status": "needs_confirm",
        "confirm": {"tool": "run_script", "title": "run bash", "preview": "\n".join(f"echo {i}" for i in range(20))},
    }
    assert notice_script_body(tall) == ""
