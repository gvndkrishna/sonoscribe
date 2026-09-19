import time

from sonoscribe.scout.harness import (
    FOLLOW_UP_CAP,
    LAST_ROUND_PROMPT,
    LAST_LIBRARY_PROMPT,
    LAST_WEATHER_PROMPT,
    MAX_ROUNDS,
    SYSTEM_PROMPT,
    ScoutBusy,
    ScoutRunner,
    follow_up_user_message,
    set_brief_notice,
    spoken_confirm,
    stamp_scout_prompt,
)
from sonoscribe.scout.render import answer_plain, parse_answer
from sonoscribe.scout.tools import wrap_untrusted


def test_system_prompt_opens_sites_in_browser() -> None:
    assert "open_page" in SYSTEM_PROMPT
    assert "nasa.gov" in SYSTEM_PROMPT
    assert "spoken helper" in SYSTEM_PROMPT
    assert "YouTube" in SYSTEM_PROMPT
    assert "unofficial hosts" in SYSTEM_PROMPT
    assert '"blurb"' in SYSTEM_PROMPT
    assert "menu bar notice" in SYSTEM_PROMPT
    assert "denser" in SYSTEM_PROMPT
    assert "AccuWeather" in SYSTEM_PROMPT
    assert "weather" in SYSTEM_PROMPT
    assert "wttr.in" in SYSTEM_PROMPT
    assert "Brooklyn" in SYSTEM_PROMPT
    assert "Queens" in SYSTEM_PROMPT
    assert '"insert"' in SYSTEM_PROMPT
    assert "Call weather now" in LAST_WEATHER_PROMPT
    assert "upsert" in LAST_LIBRARY_PROMPT
    assert "Never say you added it" in LAST_LIBRARY_PROMPT
    assert "calendar date" in SYSTEM_PROMPT
    assert "next Monday" in SYSTEM_PROMPT
    assert "every friday" in SYSTEM_PROMPT
    assert "Do not use memory" in SYSTEM_PROMPT
    assert "capture_screen" in SYSTEM_PROMPT
    assert "menu-bar notice" in SYSTEM_PROMPT
    assert "library tool" in SYSTEM_PROMPT
    assert "vocanote" in SYSTEM_PROMPT
    assert "do not invent" in LAST_ROUND_PROMPT
    assert MAX_ROUNDS == 3
    assert FOLLOW_UP_CAP == 1500


def test_stamp_scout_prompt_marks_source() -> None:
    assert stamp_scout_prompt("weather in chicago", "prefix") == "Scout: weather in chicago"
    assert stamp_scout_prompt("open the latest gta 6 trailer", "fallback") == (
        "Command mode, no match: open the latest gta 6 trailer"
    )


def test_parse_answer_wraps_prose() -> None:
    answer = parse_answer("52 and raining")
    assert answer["blocks"][0]["type"] == "lead"
    assert "52" in answer["blocks"][0]["text"]
    assert answer["blurb"] == "52 and raining"


def test_parse_answer_accepts_json() -> None:
    answer = parse_answer(
        '{"kind":"qa","title":"chicago","blurb":"52°","blocks":[{"type":"lead","text":"52 F"}]}'
    )
    assert answer["title"] == "chicago"
    assert answer["blurb"] == "52°"
    assert answer["blocks"][0]["text"] == "52 F"


def test_parse_answer_clips_long_blurb() -> None:
    answer = parse_answer(
        '{"kind":"qa","title":"long","blurb":"one two three four five six seven eight nine ten",'
        '"blocks":[{"type":"lead","text":"ok"}]}'
    )
    assert answer["blurb"] == "one two three four five six seven eight"


def test_parse_answer_repairs_missing_blocks_closer() -> None:
    raw = (
        '{"kind":"qa","title":"endgame ticket search opened","blocks":['
        '{"type":"lead","text":"Opened Chrome and ran a search for Avengers: Endgame tickets on BookMyShow, plus checked again for fresh booking news."},'
        '{"type":"facts","rows":[["Chrome action","Opened Google search for \'avengers endgame tickets bookmyshow\'"],'
        '["2026 re-release","Still confirmed by Marvel/Disney, tied to Avengers: Doomsday lead-up"],'
        '["BookMyShow booking window","No evidence found that tickets have opened yet"]]},'
        '{"type":"note","text":"My second search attempt returned no new hits, so nothing has changed since the earlier brief. The Chrome window is open on the search results page — check there directly for your city, since BookMyShow listings for special screenings can appear suddenly and sell out fast."},'
        '{"type":"links","items":[{"label":"BookMyShow","url":"https://in.bookmyshow.com"}]}}'
    )
    answer = parse_answer(raw)
    types = [block["type"] for block in answer["blocks"]]
    assert answer["title"] == "endgame ticket search opened"
    assert types == ["lead", "facts", "note", "links"]
    assert answer["blocks"][0]["text"].startswith("Opened Chrome")
    assert answer["blocks"][-1]["items"][0]["url"] == "https://in.bookmyshow.com"
    recovered = parse_answer({"kind": "qa", "title": "", "blocks": [{"type": "lead", "text": raw}]})
    assert [block["type"] for block in recovered["blocks"]] == types


def test_untrusted_wrap() -> None:
    assert wrap_untrusted("hello").startswith("untrusted web text:")
    assert wrap_untrusted("untrusted web text:\nhi").count("untrusted web text:") == 1


def test_finish_notifies_brief(monkeypatch) -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key

    update_settings({"lock": {"enabled": True, "method": "pin"}, "scout": {"provider": "openai"}})
    set_scout_key("openai", "sk-test")
    seen: list[dict] = []
    set_brief_notice(seen.append)
    runner = ScoutRunner(
        complete=lambda *_args: {
            "content": '{"kind":"qa","title":"lake wind","blocks":[{"type":"lead","text":"12"}]}',
            "tool_calls": [],
        }
    )
    runner.start("wind on the lake")
    for _ in range(40):
        current = runner.current()
        if current and current["status"] == "done":
            break
        time.sleep(0.05)
    assert runner.current()["status"] == "done"
    assert seen
    assert seen[0]["status"] == "done"
    assert seen[0]["title"] == "lake wind"
    assert seen[0]["answer"]["blurb"] == "12"
    assert seen[0]["id"]
    runner.close()


def test_cancel_does_not_notify_brief(monkeypatch) -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key

    update_settings({"lock": {"enabled": True, "method": "pin"}, "scout": {"provider": "openai"}})
    set_scout_key("openai", "sk-test")
    seen: list[dict] = []
    set_brief_notice(seen.append)

    def hang(*_args):
        time.sleep(2)
        return {"content": "{}", "tool_calls": []}

    runner = ScoutRunner(complete=hang)
    runner.start("wind on the lake")
    time.sleep(0.05)
    runner.cancel()
    assert seen == []
    runner.close()


def test_missing_key_records_error(monkeypatch) -> None:
    from sonoscribe.settings import update_settings

    update_settings({"lock": {"enabled": True, "method": "pin"}})
    runner = ScoutRunner(complete=lambda *_args: {"content": "{}", "tool_calls": []})
    run = runner.start("weather in chicago")
    assert run["status"] == "error"
    assert "key" in run["error"]


def test_loop_finishes_with_json_answer(monkeypatch) -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key

    update_settings({"lock": {"enabled": True, "method": "pin"}, "scout": {"provider": "openai", "model": "gpt-4o-mini"}})
    set_scout_key("openai", "sk-test")
    runner = ScoutRunner(
        complete=lambda *_args: {
            "content": '{"kind":"qa","title":"ok","blocks":[{"type":"lead","text":"done"}]}',
            "tool_calls": [],
        }
    )
    run = runner.start("say hello")
    for _ in range(40):
        current = runner.current()
        if current and current["status"] == "done":
            break
        time.sleep(0.05)
    current = runner.current()
    assert current["status"] == "done"
    assert current["title"] == "ok"
    assert current["answer"]["blocks"][0]["text"] == "done"
    runner.close()


def test_last_round_answers_without_tools(monkeypatch) -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key

    update_settings({"lock": {"enabled": True, "method": "pin"}, "scout": {"provider": "openai"}})
    set_scout_key("openai", "sk-test")
    seen = []

    def complete(messages, _settings, _key, allow_tools=True):
        seen.append(allow_tools)
        if not allow_tools:
            return {
                "content": '{"kind":"qa","title":"asia","blocks":[{"type":"lead","text":"Asia"}]}',
                "tool_calls": [{"id": "x", "name": "search", "arguments": {"query": "continent"}}],
            }
        return {
            "content": "",
            "tool_calls": [{"id": "1", "name": "search", "arguments": {"query": "largest continent"}}],
        }

    runner = ScoutRunner(complete=complete)
    runner._invoke = lambda name, args: "Asia is the largest continent"
    runner.start("largest continent")
    for _ in range(40):
        current = runner.current()
        if current and current["status"] in {"done", "error"}:
            break
        time.sleep(0.05)
    current = runner.current()
    assert current["status"] == "done"
    assert current["answer"]["blocks"][0]["text"] == "Asia"
    assert False in seen
    assert seen[-1] is False
    runner.close()


def test_weather_ask_can_call_weather_on_last_round(monkeypatch) -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key

    update_settings({"lock": {"enabled": True, "method": "pin"}, "scout": {"provider": "openai"}})
    set_scout_key("openai", "sk-test")
    used: list[str] = []

    def complete(messages, _settings, _key, allow_tools=True, tools=None):
        names = {item.get("name") for item in (tools or [])}
        if allow_tools and names == {"weather"}:
            return {
                "content": "",
                "tool_calls": [{"id": "w", "name": "weather", "arguments": {"place": "Queens"}}],
            }
        if allow_tools:
            return {
                "content": "",
                "tool_calls": [{"id": "1", "name": "search", "arguments": {"query": "temple queens"}}],
            }
        return {
            "content": '{"kind":"qa","title":"queens weather","blocks":[{"type":"lead","text":"19 C in Queens"}]}',
            "tool_calls": [],
        }

    runner = ScoutRunner(complete=complete)
    runner._invoke = lambda name, args: used.append(name) or (
        "live weather: Queens: +19°C" if name == "weather" else "wiki"
    )
    runner.start("what is the temperature in Queens")
    for _ in range(40):
        current = runner.current()
        if current and current["status"] in {"done", "error"}:
            break
        time.sleep(0.05)
    current = runner.current()
    assert current["status"] == "done"
    assert "weather" in used
    assert "19" in current["answer"]["blocks"][0]["text"]
    runner.close()


def test_reminder_ask_can_call_library_on_last_round(monkeypatch) -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key
    from sonoscribe.scribe.store import list_vocanotes

    update_settings({"lock": {"enabled": True, "method": "pin"}, "scout": {"provider": "openai"}})
    set_scout_key("openai", "sk-test")

    def complete(messages, _settings, _key, allow_tools=True, tools=None):
        names = {item.get("name") for item in (tools or [])}
        if allow_tools and names == {"library"}:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "lib",
                        "name": "library",
                        "arguments": {
                            "action": "upsert",
                            "kind": "vocanote",
                            "item": {
                                "title": "Avengers: Doomsday",
                                "is_reminder": True,
                                "due_at": "December 18, 2026",
                            },
                        },
                    }
                ],
            }
        if allow_tools:
            return {
                "content": "",
                "tool_calls": [{"id": "1", "name": "search", "arguments": {"query": "Avengers Doomsday"}}],
            }
        return {
            "content": '{"kind":"qa","title":"avengers doomsday","blocks":[{"type":"lead","text":"December 18, 2026"}]}',
            "tool_calls": [],
        }

    runner = ScoutRunner(complete=complete)
    real_invoke = runner._invoke

    def invoke(name, args):
        if name == "search":
            return "Avengers: Doomsday December 18, 2026"
        return real_invoke(name, args)

    runner._invoke = invoke
    runner.start("when is avengers doomsday releasing added to the reminders list")
    for _ in range(40):
        current = runner.current()
        if current and current["status"] in {"done", "error"}:
            break
        time.sleep(0.05)
    current = runner.current()
    assert current["status"] == "done"
    notes = list_vocanotes()
    assert any(item["title"] == "Avengers: Doomsday" for item in notes)
    due = next(item["due_at"] for item in notes if item["title"] == "Avengers: Doomsday")
    assert "2026-12-18" in due
    runner.close()


def test_last_round_does_not_dump_search_misses(monkeypatch) -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key

    update_settings({"lock": {"enabled": True, "method": "pin"}, "scout": {"provider": "openai"}})
    set_scout_key("openai", "sk-test")

    def complete(messages, _settings, _key, allow_tools=True):
        if not allow_tools:
            return {"content": "", "tool_calls": []}
        return {
            "content": "",
            "tool_calls": [{"id": "1", "name": "search", "arguments": {"query": "epicenter"}}],
        }

    runner = ScoutRunner(complete=complete)
    runner._invoke = lambda name, args: wrap_untrusted("No search hits.")
    runner.start("what is its epicenter")
    for _ in range(40):
        current = runner.current()
        if current and current["status"] in {"done", "error"}:
            break
        time.sleep(0.05)
    current = runner.current()
    text = answer_plain(current["answer"])
    assert "untrusted web text" not in text
    assert "No search hits" not in text
    runner.close()


def test_second_task_is_busy(monkeypatch) -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key

    update_settings({"lock": {"enabled": True, "method": "pin"}, "scout": {"provider": "openai"}})
    set_scout_key("openai", "sk-test")

    def hang(*_args):
        time.sleep(0.4)
        return {"content": '{"blocks":[{"type":"lead","text":"x"}]}', "tool_calls": []}

    runner = ScoutRunner(complete=hang)
    runner.start("one")
    try:
        runner.start("two")
        raise AssertionError("expected busy")
    except ScoutBusy:
        pass
    runner.close()


def test_spoken_confirm_yes(tmp_path, monkeypatch) -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key
    from sonoscribe.scout import set_runner

    monkeypatch.setattr("sonoscribe.scout.tools._HOME", tmp_path)
    update_settings({"lock": {"enabled": True, "method": "pin"}, "scout": {"provider": "openai"}})
    set_scout_key("openai", "sk-test")
    target = str(tmp_path / "x.txt")

    def complete(messages, _settings, _key):
        if any(item.get("role") == "tool" for item in messages):
            return {"content": '{"blocks":[{"type":"lead","text":"wrote"}]}', "tool_calls": []}
        return {
            "content": "",
            "tool_calls": [
                {"id": "1", "name": "write_file", "arguments": {"path": target, "content": "hi"}}
            ],
        }

    runner = ScoutRunner(complete=complete)
    set_runner(runner)
    runner.start("write a file")
    for _ in range(40):
        if runner.waiting_confirm():
            break
        time.sleep(0.05)
    assert runner.waiting_confirm()
    assert spoken_confirm("yes") is True
    for _ in range(40):
        current = runner.current()
        if current and current["status"] in {"done", "error"}:
            break
        time.sleep(0.05)
    assert runner.current()["status"] in {"done", "error"}
    runner.close()


def test_follow_up_reuses_brief_and_keeps_title(monkeypatch) -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key
    from sonoscribe.scout.store import set_continue, upsert_run

    update_settings({"lock": {"enabled": True, "method": "pin"}, "scout": {"provider": "openai"}})
    set_scout_key("openai", "sk-test")
    upsert_run(
        {
            "id": "tsk-keep",
            "prompt": "weather in chicago",
            "status": "done",
            "title": "chicago weather",
            "answer": {"kind": "qa", "title": "chicago weather", "blocks": [{"type": "lead", "text": "52 and windy"}]},
        },
        active=False,
    )
    set_continue("tsk-keep")
    seen: list[list[dict]] = []

    def complete(messages, _settings, _key):
        seen.append(messages)
        return {
            "content": '{"kind":"qa","title":"should not stick","blocks":[{"type":"lead","text":"colder tonight"}]}',
            "tool_calls": [],
        }

    runner = ScoutRunner(complete=complete)
    runner.start("make it shorter")
    for _ in range(40):
        current = runner.current()
        if current and current["status"] == "done":
            break
        time.sleep(0.05)
    current = runner.current()
    assert current["id"] == "tsk-keep"
    assert current["status"] == "done"
    assert current["title"] == "chicago weather"
    assert current["prompt"] == "weather in chicago"
    assert current["follow_up"] == "make it shorter"
    assert current["answer"]["blocks"][0]["text"] == "colder tonight"
    assert current["turns"][0]["prompt"] == "weather in chicago"
    assert current["turns"][0]["answer"]["blocks"][0]["text"] == "52 and windy"
    assert current["turns"][1]["prompt"] == "make it shorter"
    assert current["turns"][1]["answer"]["blocks"][0]["text"] == "colder tonight"
    user = seen[0][1]["content"]
    assert "User: weather in chicago" in user
    assert "52 and windy" in user
    assert "Follow-up: make it shorter" in user
    runner.close()


def test_follow_up_does_not_count_as_new_scout(monkeypatch) -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key
    from sonoscribe.scout.store import set_continue, upsert_run

    update_settings({"lock": {"enabled": True, "method": "pin"}, "scout": {"provider": "openai"}})
    set_scout_key("openai", "sk-test")
    upsert_run(
        {
            "id": "tsk-count",
            "prompt": "weather in chicago",
            "status": "done",
            "title": "chicago weather",
            "answer": {"kind": "qa", "title": "chicago weather", "blocks": [{"type": "lead", "text": "52"}]},
        },
        active=False,
    )
    set_continue("tsk-count")
    recorded: list[dict] = []

    class FakeStats:
        def record_scout(self, label, **kwargs):
            recorded.append({"label": label, **kwargs})

    runner = ScoutRunner(
        complete=lambda *_args: {
            "content": '{"kind":"qa","title":"no","blocks":[{"type":"lead","text":"colder"}]}',
            "tool_calls": [],
            "input_tokens": 10,
            "output_tokens": 4,
        }
    )
    runner.start("make it shorter", stats=FakeStats())
    for _ in range(40):
        current = runner.current()
        if current and current["status"] == "done":
            break
        time.sleep(0.05)
    assert runner.current()["status"] == "done"
    assert recorded
    assert recorded[0]["count"] is False
    runner.close()


def test_follow_up_user_message_includes_prior_answer() -> None:
    text = follow_up_user_message(
        {
            "title": "lake wind",
            "prompt": "wind on the lake",
            "follow_up": "in knots",
            "answer": {"blocks": [{"type": "lead", "text": "12 knots"}]},
        },
        "say it in km/h",
    )
    assert "Title: lake wind" in text
    assert "User: wind on the lake" in text
    assert "User: in knots" in text
    assert "12 knots" in text
    assert "Follow-up: say it in km/h" in text


def test_answer_plain_flattens_blocks() -> None:
    text = answer_plain(
        {
            "blocks": [
                {"type": "lead", "text": "52 F"},
                {"type": "facts", "rows": [["wind", "12"]]},
                {"type": "list", "items": ["bring a coat"]},
            ]
        }
    )
    assert "52 F" in text
    assert "wind: 12" in text
    assert "bring a coat" in text


def test_start_without_lock_is_error() -> None:
    runner = ScoutRunner(complete=lambda *_args: {"content": "{}", "tool_calls": []})
    run = runner.start("weather in chicago")
    assert run["status"] == "error"
    assert "lock" in run["error"]


def test_token_cap_answers_on_last_round() -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key

    update_settings(
        {
            "lock": {"enabled": True, "method": "pin"},
            "scout": {"provider": "openai", "max_tokens": 2000},
        }
    )
    set_scout_key("openai", "sk-test")
    seen = []

    def complete(messages, _settings, _key, allow_tools=True):
        seen.append(allow_tools)
        if not allow_tools:
            return {
                "content": '{"kind":"qa","title":"cap","blocks":[{"type":"lead","text":"done"}]}',
                "tool_calls": [],
            }
        return {
            "content": "",
            "tool_calls": [{"id": "1", "name": "search", "arguments": {"query": "x"}}],
            "input_tokens": 2500,
            "output_tokens": 10,
        }

    runner = ScoutRunner(complete=complete)
    runner._invoke = lambda name, args: "ok"
    runner.start("hello")
    for _ in range(40):
        current = runner.current()
        if current and current["status"] in {"done", "error"}:
            break
        time.sleep(0.05)
    current = runner.current()
    assert current["status"] == "done"
    assert False in seen
    runner.close()


def test_no_task_limits_keep_tools() -> None:
    from sonoscribe.settings import update_settings
    from sonoscribe.scout.keys import set_scout_key

    update_settings(
        {
            "lock": {"enabled": True, "method": "pin"},
            "scout": {"provider": "openai", "max_tokens": 0, "duration_sec": 0},
        }
    )
    set_scout_key("openai", "sk-test")
    seen = []

    def complete(messages, _settings, _key, allow_tools=True):
        seen.append(allow_tools)
        if allow_tools:
            return {
                "content": "",
                "tool_calls": [{"id": "1", "name": "search", "arguments": {"query": "x"}}],
                "input_tokens": 0,
                "output_tokens": 0,
            }
        return {
            "content": '{"kind":"qa","title":"open","blocks":[{"type":"lead","text":"ok"}]}',
            "tool_calls": [],
        }

    runner = ScoutRunner(complete=complete)
    runner._invoke = lambda name, args: "ok"
    runner.start("hello")
    for _ in range(40):
        current = runner.current()
        if current and current["status"] in {"done", "error"}:
            break
        time.sleep(0.05)
    current = runner.current()
    assert current["status"] == "done"
    assert seen[0] is True
    runner.close()
