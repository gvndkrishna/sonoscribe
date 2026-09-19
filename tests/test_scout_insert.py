from sonoscribe.scout.harness import SYSTEM_PROMPT, ScoutRunner, request_insert, set_brief_insert, start_scout
from sonoscribe.scout.insert import (
    can_insert,
    insert_text_from_answer,
    insert_text_from_run,
    needs_restore_app,
    notice_holds_bubble,
    notice_shows_insert,
    parse_insert_ask,
)
from sonoscribe.scout.render import parse_answer
from sonoscribe.notify import notice_insert_label


def test_parse_insert_ask_strips_lead_and_auto_tail() -> None:
    lead = parse_insert_ask("insert a thank you to Alex")
    assert lead["prompt"] == "a thank you to Alex"
    assert lead["auto_insert"] is False
    assert lead["want_insert"] is True
    auto = parse_insert_ask("write a thank you and insert it")
    assert auto["prompt"] == "write a thank you"
    assert auto["auto_insert"] is True
    assert auto["want_insert"] is True
    both = parse_insert_ask("insert a thank you to Alex and insert it")
    assert both["prompt"] == "a thank you to Alex"
    assert both["auto_insert"] is True
    paste = parse_insert_ask("draft a reply and paste it")
    assert paste["prompt"] == "draft a reply"
    assert paste["auto_insert"] is True
    assert parse_insert_ask("insert this a poem about rain")["prompt"] == "a poem about rain"
    weather = parse_insert_ask("weather in queens")
    assert weather["want_insert"] is False
    assert weather["auto_insert"] is False


def test_insert_text_prefers_answer_field() -> None:
    answer = parse_answer(
        {
            "kind": "qa",
            "title": "thank you",
            "insert": "Thanks, Alex. See you Thursday.",
            "blocks": [{"type": "lead", "text": "Here is a draft."}],
        }
    )
    assert answer["insert"] == "Thanks, Alex. See you Thursday."
    assert insert_text_from_answer(answer) == "Thanks, Alex. See you Thursday."
    fallback = {"blocks": [{"type": "lead", "text": "52 and sunny"}]}
    assert insert_text_from_answer(fallback) == "52 and sunny"
    code = {"blocks": [{"type": "code", "text": "print(1)"}]}
    assert insert_text_from_answer(code) == "print(1)"


def test_restore_app_only_when_focus_moved() -> None:
    notes = {"bundle_id": "com.apple.Notes", "name": "Notes"}
    chrome = {"bundle_id": "com.google.Chrome", "name": "Chrome"}
    assert needs_restore_app(notes, chrome) is True
    assert needs_restore_app(notes, notes) is False
    assert needs_restore_app({}, chrome) is False
    assert needs_restore_app(notes, None) is False


def test_notice_insert_holds_until_click() -> None:
    run = {
        "id": "tsk-1",
        "status": "done",
        "auto_insert": False,
        "want_insert": True,
        "insert_text": "Thanks, Alex.",
        "answer": {"blocks": [{"type": "lead", "text": "Thanks, Alex."}]},
    }
    assert can_insert(run) is True
    assert notice_shows_insert(run) is True
    assert notice_holds_bubble(run) is True
    auto = {**run, "auto_insert": True}
    assert notice_shows_insert(auto) is False
    assert notice_holds_bubble(auto) is False
    assert notice_insert_label() == "insert"
    assert can_insert({**run, "status": "thinking"}) is False
    weather = {
        "id": "tsk-w",
        "status": "done",
        "want_insert": False,
        "insert_text": "Queens: +19°C",
        "answer": {"blocks": [{"type": "lead", "text": "Queens: +19°C"}]},
    }
    assert can_insert(weather) is False
    assert notice_shows_insert(weather) is False
    assert notice_holds_bubble(weather) is False
    script = {
        "id": "tsk-script",
        "status": "needs_confirm",
        "confirm": {"tool": "run_script", "title": "run bash", "preview": "echo hello"},
    }
    write = {
        "id": "tsk-write",
        "status": "needs_confirm",
        "confirm": {"tool": "write_file", "title": "write file", "preview": "notes.txt"},
    }
    assert notice_holds_bubble(script) is True
    assert notice_holds_bubble(write) is True


def test_start_scout_strips_insert_phrase(monkeypatch) -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key

    update_settings({"lock": {"enabled": True, "method": "pin"}, "scout": {"provider": "openai"}})
    set_scout_key("openai", "sk-test")
    inserted: list[dict] = []
    set_brief_insert(inserted.append)

    def complete(*_args, **_kwargs):
        return {
            "content": '{"kind":"qa","title":"thank you","insert":"Thanks, Alex.","blocks":[{"type":"lead","text":"draft ready"}]}',
            "tool_calls": [],
        }

    runner = ScoutRunner(complete=complete)
    run = runner.start(
        "insert a thank you to Alex and insert it",
        frontmost={"bundle_id": "com.apple.Notes", "name": "Notes"},
    )
    for _ in range(40):
        current = runner.current()
        if current and current["status"] in {"done", "error"}:
            break
        import time

        time.sleep(0.05)
    current = runner.current()
    assert current["status"] == "done"
    assert current["prompt"] == "a thank you to Alex"
    assert current["auto_insert"] is True
    assert current["want_insert"] is True
    assert current["insert_text"] == "Thanks, Alex."
    assert current["frontmost"]["bundle_id"] == "com.apple.Notes"
    assert inserted
    assert insert_text_from_run(inserted[0]) == "Thanks, Alex."
    runner.close()


def test_request_insert_needs_done_text() -> None:
    from sonoscribe.scout.store import upsert_run

    upsert_run(
        {
            "id": "tsk-ins",
            "prompt": "write a note",
            "status": "done",
            "want_insert": True,
            "answer": {"kind": "qa", "title": "note", "insert": "Hello", "blocks": [{"type": "lead", "text": "Hello"}]},
        },
        active=False,
    )
    seen: list[dict] = []
    set_brief_insert(seen.append)
    run = request_insert("tsk-ins")
    assert run is not None
    assert seen[0]["id"] == "tsk-ins"
    assert request_insert("missing") is None
    upsert_run(
        {
            "id": "tsk-weather",
            "prompt": "weather in queens",
            "status": "done",
            "answer": {"kind": "qa", "title": "queens", "blocks": [{"type": "lead", "text": "19 C"}]},
        },
        active=False,
    )
    assert request_insert("tsk-weather") is None


def test_prompt_mentions_insert_field() -> None:
    assert '"insert"' in SYSTEM_PROMPT
    assert "Do not paste it yourself" in SYSTEM_PROMPT


def test_start_scout_export_accepts_frontmost() -> None:
    from sonoscribe.settings import update_settings

    update_settings({"lock": {"enabled": True, "method": "pin"}})
    run = start_scout("hello", frontmost={"bundle_id": "com.apple.TextEdit", "name": "TextEdit"})
    assert run["status"] == "error"
    assert run["frontmost"]["bundle_id"] == "com.apple.TextEdit"
