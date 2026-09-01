from sonoscribe.stats import StatsStore, average_wpm, count_words, public_stats


def test_average_wpm() -> None:
    assert average_wpm({"dictation_words": 120, "dictation_seconds": 60}) == 120
    assert average_wpm({"dictation_words": 0, "dictation_seconds": 10}) == 0.0
    assert average_wpm({"dictation_words": 90, "dictation_seconds": 0}) == 0.0


def test_count_words() -> None:
    assert count_words("hello there world") == 3
    assert count_words("") == 0


def test_store_records_and_persists(tmp_path) -> None:
    path = tmp_path / "stats.json"
    store = StatsStore(path)
    store.record_dictation("one two three four", 2.0)
    store.record_command("Enter")
    store.record_routine("work")
    snap = store.snapshot()
    assert snap["dictation_words"] == 4
    assert snap["command_runs"] == 1
    assert snap["routine_runs"] == 1
    assert snap["average_wpm"] == 120.0
    assert snap["activity"][0]["kind"] == "routine"

    again = StatsStore(path).snapshot()
    assert again["command_runs"] == 1
    assert again["dictation_words"] == 4


def test_public_stats_shape() -> None:
    data = public_stats(
        {
            "dictation_words": 10,
            "dictation_seconds": 5,
            "command_runs": 2,
            "routine_runs": 1,
            "activity": [],
        }
    )
    assert data["average_wpm"] == 120.0
