from datetime import datetime, timedelta, timezone

from sonoscribe.scout.store import (
    clean_store,
    default_title,
    delete_runs,
    load_store,
    save_store,
    set_continue,
    set_run_title,
    take_continue_run,
    upsert_run,
)


def test_default_title_trims() -> None:
    assert default_title("weather") == "weather"
    assert default_title("") == "brief"
    long = "what is the weather like in chicago this afternoon"
    assert default_title(long) == long[:47].rsplit(" ", 1)[0]


def test_title_and_delete(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_SCOUT", str(tmp_path / "scout.json"))
    from sonoscribe.scout.store import clear_scout_cache

    clear_scout_cache()
    upsert_run(
        {
            "id": "tsk-a",
            "prompt": "weather in chicago",
            "status": "done",
            "answer": {"kind": "qa", "title": "chicago weather", "blocks": []},
        },
        active=False,
    )
    upsert_run({"id": "tsk-b", "prompt": "second", "status": "error", "error": "no"}, active=False)
    run = set_run_title("tsk-a", "lake wind")
    assert run["title"] == "lake wind"
    assert load_store()["runs"][0]["title"] in {"lake wind", "second"}
    saved = delete_runs(["tsk-b"])
    ids = [item["id"] for item in saved["runs"]]
    assert "tsk-b" not in ids
    assert "tsk-a" in ids
    clear_scout_cache()


def test_purge_old_briefs_and_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_SCOUT", str(tmp_path / "scout.json"))
    from sonoscribe.scout.store import clear_scout_cache

    clear_scout_cache()
    now = datetime.now(timezone.utc)
    stale_brief = (now - timedelta(days=11)).isoformat(timespec="seconds")
    stale_error = (now - timedelta(days=2)).isoformat(timespec="seconds")
    fresh = now.isoformat(timespec="seconds")
    cleaned = clean_store(
        {
            "runs": [
                {"id": "old-ok", "created_at": stale_brief, "prompt": "old", "status": "done"},
                {"id": "old-err", "created_at": stale_error, "prompt": "err", "status": "error"},
                {"id": "new-ok", "created_at": fresh, "prompt": "new", "status": "done", "answer": {"title": "kept"}},
                {"id": "live", "created_at": stale_brief, "prompt": "live", "status": "thinking"},
            ]
        }
    )
    ids = {item["id"] for item in cleaned["runs"]}
    assert ids == {"new-ok", "live"}
    assert next(item["title"] for item in cleaned["runs"] if item["id"] == "new-ok") == "kept"
    save_store(cleaned)
    clear_scout_cache()


def test_continue_target_and_updated_at_keeps_brief(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_SCOUT", str(tmp_path / "scout.json"))
    from sonoscribe.scout.store import clear_scout_cache, continue_id

    clear_scout_cache()
    upsert_run(
        {
            "id": "tsk-old",
            "prompt": "weather",
            "status": "done",
            "title": "chicago weather",
            "created_at": "2020-01-01T00:00:00+00:00",
            "answer": {"blocks": [{"type": "lead", "text": "52"}]},
        },
        active=False,
    )
    stored = set_continue("tsk-old")
    assert stored["continue_id"] == "tsk-old"
    taken = take_continue_run()
    assert taken["id"] == "tsk-old"
    assert continue_id() == ""
    now = datetime.now(timezone.utc)
    cleaned = clean_store(
        {
            "runs": [
                {
                    "id": "kept-follow",
                    "created_at": (now - timedelta(days=11)).isoformat(timespec="seconds"),
                    "updated_at": now.isoformat(timespec="seconds"),
                    "prompt": "old",
                    "status": "done",
                }
            ]
        }
    )
    assert {item["id"] for item in cleaned["runs"]} == {"kept-follow"}
    clear_scout_cache()


def test_scout_numbers_and_stack_refs() -> None:
    from sonoscribe.scout.store import history, resolve_scout_ref

    upsert_run({"id": "tsk-earlier", "prompt": "earlier", "status": "done", "title": "earlier brief"}, active=False)
    upsert_run({"id": "tsk-later", "prompt": "later", "status": "done", "title": "later brief"}, active=False)
    numbered = history()
    assert numbered[0]["id"] == "tsk-later"
    assert numbered[0]["sku"] == "sc–01"
    assert numbered[1]["id"] == "tsk-earlier"
    assert numbered[1]["sku"] == "sc–02"
    assert resolve_scout_ref(0)["id"] == "tsk-later"
    assert resolve_scout_ref(1)["id"] == "tsk-later"
    assert resolve_scout_ref("-1")["id"] == "tsk-earlier"
    assert resolve_scout_ref(2)["id"] == "tsk-earlier"
    assert resolve_scout_ref(9) is None


def test_loads_legacy_tasks_json(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SONOSCRIBE_SCOUT", raising=False)
    monkeypatch.delenv("SONOSCRIBE_TASKS", raising=False)
    monkeypatch.setattr("sonoscribe.scout.store.support_dir", lambda: tmp_path)
    from sonoscribe.scout.store import clear_scout_cache, load_store, save_store

    clear_scout_cache()
    (tmp_path / "tasks.json").write_text(
        '{"runs": [{"id": "tsk-old", "prompt": "weather", "status": "done", "title": "chicago"}], "active_id": "", "continue_id": ""}\n',
        encoding="utf-8",
    )
    data = load_store()
    assert data["runs"][0]["id"] == "tsk-old"
    save_store(data)
    assert (tmp_path / "scout.json").is_file()
    clear_scout_cache()


def test_open_url_is_kept() -> None:
    from sonoscribe.scout.store import get_run

    upsert_run(
        {
            "id": "tsk-open",
            "prompt": "weather",
            "status": "done",
            "open_url": "https://www.accuweather.com/en/search-locations?query=chicago",
        },
        active=False,
    )
    run = get_run("tsk-open")
    assert run is not None
    assert "accuweather.com" in run["open_url"]
