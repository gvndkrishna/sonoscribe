from datetime import datetime
from zoneinfo import ZoneInfo

from sonoscribe.stats import (
    StatsStore,
    average_wpm,
    chart_series,
    clean_stats_blob,
    count_words,
    merge_stats_blobs,
    public_stats,
)


def test_average_wpm() -> None:
    assert average_wpm({"dictation_words": 120, "dictation_seconds": 60}) == 120
    assert average_wpm({"dictation_words": 0, "dictation_seconds": 10}) == 0.0
    assert average_wpm({"dictation_words": 90, "dictation_seconds": 0}) == 0.0


def test_count_words() -> None:
    assert count_words("hello there world") == 3
    assert count_words("") == 0


def test_merge_stats_blobs_keeps_highest_counts_and_union_activity() -> None:
    merged = merge_stats_blobs(
        {
            "command_runs": 2,
            "dictation_words": 10,
            "dictation_runs": 3,
            "activity": [{"at": "2026-02-01T00:00:00+00:00", "kind": "command", "label": "Save"}],
        },
        {
            "command_runs": 9,
            "dictation_words": 4,
            "dictation_runs": 1,
            "activity": [{"at": "2026-01-01T00:00:00+00:00", "kind": "command", "label": "Mute"}],
        },
    )
    assert merged["command_runs"] == 9
    assert merged["dictation_words"] == 10
    assert merged["dictation_runs"] == 3
    labels = {item["label"] for item in merged["activity"]}
    assert labels == {"Save", "Mute"}


def test_store_records_and_persists(tmp_path) -> None:
    path = tmp_path / "stats.json"
    store = StatsStore(path)
    store.record_dictation("one two three four", 2.0)
    store.record_command("Enter", "keyboard")
    store.record_routine("work")
    store.record_scout("weather in chicago")
    snap = store.snapshot()
    assert snap["dictation_words"] == 4
    assert snap["dictation_runs"] == 1
    assert snap["command_runs"] == 1
    assert snap["routine_runs"] == 1
    assert snap["scout_runs"] == 1
    assert snap["average_wpm"] == 120.0
    assert snap["activity"][0]["kind"] == "scout"
    command_event = next(item for item in snap["activity"] if item["kind"] == "command")
    assert command_event["command_type"] == "keyboard"

    store.record_scout("asia", model="gpt-4o-mini", provider="openai", input_tokens=1000, output_tokens=200, cost=0.00027)
    snap = store.snapshot()
    assert snap["scout_runs"] == 2
    tokens = snap["charts"]["scout_tokens"]
    assert tokens[0]["id"] == "gpt-4o-mini"
    assert tokens[0]["count"] == 1200
    assert any(item["cost"] for item in snap["charts"]["scout_cost"])
    store.record_scout("asia again", model="gpt-4o-mini", input_tokens=100, output_tokens=20, cost=0.00004, count=False)
    snap = store.snapshot()
    assert snap["scout_runs"] == 2
    assert snap["activity"][0]["follow_up"] is True
    assert snap["charts"]["by_kind"]["scout"] == 2
    assert snap["charts"]["scout_tokens"][0]["count"] == 1320

    again = StatsStore(path).snapshot()
    assert again["command_runs"] == 1
    assert again["dictation_words"] == 4


def test_private_mode_skips_stats_writes(tmp_path) -> None:
    from sonoscribe.settings import update_settings

    path = tmp_path / "stats.json"
    store = StatsStore(path)
    store.record_command("Enter", "keyboard")
    update_settings({"private_mode": True})
    store.record_dictation("one two three four", 2.0)
    store.record_command("Mute", "system")
    store.record_routine("work")
    store.record_scout("weather")
    snap = store.snapshot()
    assert snap["command_runs"] == 1
    assert snap["dictation_words"] == 0
    assert snap["routine_runs"] == 0
    assert snap["scout_runs"] == 0
    assert snap["activity"][0]["label"] == "Enter"
    update_settings({"private_mode": False})
    store.record_routine("work")
    assert store.snapshot()["routine_runs"] == 1


def test_public_stats_shape() -> None:
    data = public_stats(
        {
            "dictation_words": 10,
            "dictation_seconds": 5,
            "command_runs": 2,
            "routine_runs": 1,
            "scout_runs": 3,
            "activity": [],
        }
    )
    assert data["average_wpm"] == 120.0
    assert data["scout_runs"] == 3
    assert data["charts"]["by_kind"] == {"dictate": 0, "command": 2, "routine": 1, "scout": 3}
    assert data["charts"]["versus"] == {"dictate": 0, "command": 2}
    assert data["charts"]["versus_routines"] == {"command": 2, "routine": 1}
    assert data["charts"]["by_command_type"]["keyboard"] == 0
    assert len(data["charts"]["daily"]) == 14
    assert len(data["charts"]["usage"]) == 112
    assert data["charts"]["hourly"] == [0] * 24


def test_chart_series_buckets_activity() -> None:
    charts = chart_series(
        [
            {"at": "2026-09-07T11:00:00+00:00", "kind": "command", "label": "Mute", "command_type": "system"},
            {"at": "2026-09-07T11:05:00+00:00", "kind": "command", "label": "Mute", "command_type": "system"},
            {"at": "2026-09-07T12:00:00+00:00", "kind": "dictate", "label": "3 words"},
            {"at": "2026-09-07T12:10:00+00:00", "kind": "command", "label": "Save", "command_type": "keyboard"},
            {"at": "2026-09-07T12:20:00+00:00", "kind": "routine", "label": "work"},
            {"at": "2026-09-07T12:30:00+00:00", "kind": "scout", "label": "chicago weather"},
        ]
    )
    assert charts["by_kind"]["command"] == 3
    assert charts["by_kind"]["dictate"] == 1
    assert charts["by_kind"]["scout"] == 1
    assert charts["versus"] == {"dictate": 1, "command": 3}
    assert charts["versus_routines"] == {"command": 3, "routine": 1}
    assert charts["top_routines"][0] == {"label": "work", "count": 1}
    assert charts["by_command_type"]["system"] == 2
    assert charts["by_command_type"]["keyboard"] == 1
    assert charts["top_commands"][0] == {"label": "Mute", "count": 2}
    assert sum(charts["hourly"]) == 6
    assert any(day.get("scout") for day in charts["daily"])

    follow = chart_series(
        [
            {"at": "2026-09-07T12:40:00+00:00", "kind": "scout", "label": "chicago weather"},
            {"at": "2026-09-07T12:50:00+00:00", "kind": "scout", "label": "chicago weather", "follow_up": True},
        ]
    )
    assert follow["by_kind"]["scout"] == 1
    assert sum(day.get("scout") or 0 for day in follow["daily"]) == 1


def test_chart_series_uses_timezone() -> None:
    charts = chart_series(
        [{"at": "2026-09-07T18:30:00+00:00", "kind": "command", "label": "Mute"}],
        tz=ZoneInfo("Asia/Kolkata"),
    )
    assert charts["hourly"][0] == 1


def test_chart_series_tracks_models() -> None:
    charts = chart_series(
        [
            {
                "at": "2026-09-07T11:00:00+00:00",
                "kind": "dictate",
                "label": "4 words",
                "model": "small",
                "words": 4,
                "seconds": 2,
            },
            {
                "at": "2026-09-07T11:05:00+00:00",
                "kind": "command",
                "label": "Mute",
                "model": "large-v3-turbo",
            },
        ],
        model_labels={"small": "small", "large-v3-turbo": "large v3 turbo"},
    )
    ids = {item["id"]: item["count"] for item in charts["by_model"]}
    assert ids["small"] == 1
    assert ids["large-v3-turbo"] == 1
    assert charts["wpm_by_model"][0]["id"] == "small"
    assert charts["wpm_by_model"][0]["wpm"] == 120.0


def test_usage_heatmap_counts_model_days() -> None:
    charts = chart_series(
        [
            {
                "at": "2026-09-07T11:00:00+00:00",
                "kind": "dictate",
                "label": "4 words",
                "model": "small",
            },
            {
                "at": "2026-09-07T11:05:00+00:00",
                "kind": "command",
                "label": "Mute",
                "model": "large-v3-turbo",
            },
            {"at": "2026-09-07T11:10:00+00:00", "kind": "command", "label": "Save"},
        ]
    )
    assert len(charts["usage"]) == 112
    local_day = datetime.fromisoformat("2026-09-07T11:00:00+00:00").astimezone().date().isoformat()
    day = next(item for item in charts["usage"] if item["day"] == local_day)
    assert day["count"] == 2
    assert charts["usage"][0]["day"] < charts["usage"][-1]["day"]


def test_activity_keeps_last_2000(tmp_path) -> None:
    store = StatsStore(tmp_path / "stats.json")
    for index in range(2010):
        store.record_command(f"Command {index}")
    snap = store.snapshot()
    assert len(snap["activity"]) == 2000
    assert snap["command_runs"] == 2010
    assert snap["charts"]["by_kind"]["command"] == 2010
    assert snap["activity"][0]["label"] == "Command 2009"
    assert snap["activity"][-1]["label"] == "Command 10"


def test_snapshot_can_switch_device(tmp_path) -> None:
    from sonoscribe.settings import update_settings

    path = tmp_path / "stats.json"
    store = StatsStore(path)
    store.record_command("Enter")
    this = update_settings({"username": "studio", "sync": {"enabled": True, "what": {"stats": True}}})
    other_id = "dev-other"
    store.apply_synced_stats(
        {other_id: {"command_runs": 9, "activity": [{"kind": "command", "label": "Mute", "at": "2026-01-01T00:00:00+00:00"}]}},
        this["device"]["id"],
    )
    local = store.snapshot()
    assert local["command_runs"] == 1
    assert local["stats_synced"] is True
    remote = store.snapshot(other_id)
    assert remote["command_runs"] == 9
    assert remote["device_id"] == other_id


def test_legacy_task_stats_load_as_scout() -> None:
    blob = clean_stats_blob(
        {
            "task_runs": 4,
            "activity": [
                {"at": "2026-09-07T12:00:00+00:00", "kind": "task", "label": "weather"},
                {"at": "2026-09-07T12:10:00+00:00", "kind": "command", "label": "Enter"},
            ],
        }
    )
    assert blob["scout_runs"] == 4
    assert "task_runs" not in blob
    assert blob["activity"][0]["kind"] == "scout"
    assert blob["activity"][1]["kind"] == "command"
