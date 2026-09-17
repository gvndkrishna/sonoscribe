from sonoscribe.settings import (
    empty_settings,
    load_settings,
    public_account,
    public_settings,
    save_settings,
    update_settings,
    validate_settings,
)


def test_validate_falls_back_to_defaults() -> None:
    cleaned = validate_settings({"theme": "neon", "accent": "amber", "sync": {"enabled": 1}})
    assert cleaned["theme"] == "light"
    assert cleaned["accent"] == "amber"
    assert cleaned["sync"]["enabled"] is True
    assert cleaned["username"] == ""
    assert cleaned["device"]["id"]
    assert cleaned["sync"]["what"]["library"] is True
    assert cleaned["sync"]["what"]["stats"] is False


def test_last_error_kind_survives_clean() -> None:
    cleaned = validate_settings(
        {
            "sync": {
                "last_error": {"message": "Sign in", "details": "gcloud auth", "kind": "auth"},
            }
        }
    )
    assert cleaned["sync"]["last_error"] == {
        "message": "Sign in",
        "details": "gcloud auth",
        "kind": "auth",
    }


def test_retired_accents_map_to_palette() -> None:
    assert validate_settings({"accent": "pink"})["accent"] == "purple"
    assert validate_settings({"accent": "green"})["accent"] == "teal"
    assert validate_settings({"accent": "orange"})["accent"] == "amber"
    assert validate_settings({"accent": "red"})["accent"] == "amber"
    assert validate_settings({"accent": "neon"})["accent"] == "amber"


def test_load_and_save_roundtrip(tmp_path, monkeypatch) -> None:
    path = tmp_path / "nested" / "settings.json"
    monkeypatch.setenv("SONOSCRIBE_SETTINGS", str(path))
    from sonoscribe.settings import clear_settings_cache

    clear_settings_cache()
    saved = save_settings({**empty_settings(), "theme": "dark", "timezone": "Asia/Kolkata"})
    assert saved["theme"] == "dark"
    assert load_settings()["timezone"] == "Asia/Kolkata"
    assert load_settings() is load_settings()


def test_update_settings_patches_appearance() -> None:
    update_settings({"theme": "dark", "accent": "teal"})
    data = load_settings()
    assert data["theme"] == "dark"
    assert data["accent"] == "teal"
    assert data["timezone"] == "local"
    assert data["reduce_motion"] is False


def test_reduce_motion_defaults_and_patch() -> None:
    assert empty_settings()["reduce_motion"] is False
    assert validate_settings({})["reduce_motion"] is False
    assert validate_settings({"reduce_motion": True})["reduce_motion"] is True
    saved = update_settings({"reduce_motion": True})
    assert saved["reduce_motion"] is True
    assert load_settings()["reduce_motion"] is True
    assert public_settings()["reduce_motion"] is True
    update_settings({"reduce_motion": False})
    assert public_settings()["reduce_motion"] is False


def test_private_mode_defaults_and_patch() -> None:
    assert empty_settings()["private_mode"] is False
    assert validate_settings({})["private_mode"] is False
    assert validate_settings({"private_mode": True})["private_mode"] is True
    saved = update_settings({"private_mode": True})
    assert saved["private_mode"] is True
    assert load_settings()["private_mode"] is True
    assert public_settings()["private_mode"] is True
    assert public_account()["private_mode"] is True
    update_settings({"private_mode": False})
    assert public_settings()["private_mode"] is False
    assert public_account()["private_mode"] is False


def test_lock_defaults_and_timeout_patch() -> None:
    assert empty_settings()["lock"] == {"enabled": False, "method": "", "timeout_sec": 900}
    cleaned = validate_settings({"lock": {"enabled": True, "method": "pin", "timeout_sec": 300}})
    assert cleaned["lock"]["enabled"] is True
    assert cleaned["lock"]["method"] == "pin"
    assert cleaned["lock"]["timeout_sec"] == 300
    assert validate_settings({"lock": {"enabled": True, "method": "touch"}})["lock"]["enabled"] is False
    saved = update_settings({"lock": {"timeout_sec": 1800}})
    assert saved["lock"]["timeout_sec"] == 1800
    assert saved["lock"]["enabled"] is False


def test_private_mode_keeps_stats_preference_but_blocks_sync() -> None:
    from sonoscribe.settings import sync_what

    data = validate_settings({"private_mode": True, "sync": {"what": {"stats": True, "library": True}}})
    assert data["sync"]["what"]["stats"] is True
    assert sync_what(data)["stats"] is False
    data["private_mode"] = False
    assert sync_what(data)["stats"] is True


def test_sync_interval_defaults_and_patch() -> None:
    assert empty_settings()["sync"]["interval_sec"] == 900
    assert validate_settings({})["sync"]["interval_sec"] == 900
    assert validate_settings({"sync": {"interval_sec": 0}})["sync"]["interval_sec"] == 0
    assert validate_settings({"sync": {"interval_sec": 300}})["sync"]["interval_sec"] == 300
    assert validate_settings({"sync": {"interval_sec": 17}})["sync"]["interval_sec"] == 900
    saved = update_settings({"sync": {"interval_sec": 3600}})
    assert saved["sync"]["interval_sec"] == 3600
    assert public_settings()["sync"]["interval_sec"] == 3600
    update_settings({"sync": {"interval_sec": 0}})
    assert load_settings()["sync"]["interval_sec"] == 0


def test_update_username_and_device_name() -> None:
    update_settings({"username": "studio", "device": {"name": "Desk Mac"}})
    data = load_settings()
    assert data["username"] == "studio"
    assert data["username_updated_at"]
    assert data["device"]["name"] == "Desk Mac"
    assert data["devices"][0]["name"] == "Desk Mac"


def test_device_id_and_serial_are_not_user_writable() -> None:
    current = load_settings()
    original_id = current["device"]["id"]
    original_serial = current["device"]["serial"]
    update_settings({"device": {"id": "hacked-id", "serial": "HACKSERIAL", "name": "Desk Mac"}})
    data = load_settings()
    assert data["device"]["id"] == original_id
    assert data["device"]["serial"] == original_serial
    assert data["device"]["name"] == "Desk Mac"


def test_load_migrates_generated_id_to_serial(monkeypatch) -> None:
    import json

    from sonoscribe.catalog import load_library, save_library
    from sonoscribe.settings import clear_settings_cache, load_settings, settings_path

    monkeypatch.setattr("sonoscribe.device.hardware_serial", lambda: "C02SERIAL01")
    save_library(
        {
            "commands": [
                {
                    "type": "keyboard",
                    "name": "Here",
                    "phrases": ["only here"],
                    "action": "enter",
                    "devices": ["dev-abcdef123456"],
                }
            ],
            "routines": [],
        }
    )
    settings_path().write_text(
        json.dumps(
            {
                "theme": "light",
                "device": {"id": "dev-abcdef123456", "serial": "old", "name": "Studio"},
                "devices": [{"id": "dev-abcdef123456", "serial": "old", "name": "Studio"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    clear_settings_cache()
    data = load_settings()
    assert data["device"]["id"] == "C02SERIAL01"
    assert data["device"]["serial"] == "C02SERIAL01"
    assert all(item["id"] != "dev-abcdef123456" for item in data["devices"])
    here = next(item for item in load_library()["commands"] if item["name"] == "Here")
    assert here["devices"] == ["C02SERIAL01"]


def test_sync_what_defaults_and_patch() -> None:
    update_settings({"sync": {"what": {"stats": True, "library": False}}})
    data = load_settings()
    assert data["sync"]["what"]["stats"] is True
    assert data["sync"]["what"]["library"] is False


def test_public_settings_omits_nothing_secret() -> None:
    public = public_settings()
    assert "private_key" not in public
    assert "timezones" in public
    assert public["sync"]["enabled"] is False
    assert public["sync"]["interval_sec"] == 900
    assert public["sync_intervals"] == [0, 300, 900, 1800, 3600]
    assert public["username"] == ""
    assert public["device"]["id"]
    assert public["model"] == "large-v3-turbo"
    assert public["devices"][0]["id"] == public["device"]["id"]
    assert [item["id"] for item in public["charts"]] == [
        "mix",
        "versus",
        "types",
        "models",
        "model-wpm",
        "daily",
        "top",
        "routines",
        "routine-split",
        "hourly",
        "library",
    ]


def test_model_persists_and_rejects_unknown() -> None:
    cleaned = validate_settings({"model": "nope"})
    assert cleaned["model"] == "large-v3-turbo"
    update_settings({"model": "small"})
    assert load_settings()["model"] == "small"
    from sonoscribe.settings import resolve_model

    assert resolve_model() == "small"
    assert resolve_model("base") == "base"


def test_custom_model_roundtrip(tmp_path) -> None:
    from sonoscribe.settings import add_custom_model, lookup_model, remove_custom_model

    folder = tmp_path / "mlx-whisper"
    folder.mkdir()
    (folder / "config.json").write_text("{}", encoding="utf-8")
    (folder / "weights.npz").write_bytes(b"x")
    saved = add_custom_model(str(folder), "Desk turbo")
    spec = lookup_model(saved["model"])
    assert spec is not None
    assert spec["custom"] is True
    assert spec["path"] == str(folder.resolve())
    assert spec["label"] == "Desk turbo"
    removed = remove_custom_model(spec["id"])
    assert removed["model"] == "large-v3-turbo"
    assert lookup_model(spec["id"]) is None


def test_charts_layout_defaults_and_hides_missing() -> None:
    cleaned = validate_settings({})
    assert [item["id"] for item in cleaned["charts"]] == [
        "mix",
        "versus",
        "types",
        "models",
        "model-wpm",
        "daily",
        "top",
        "routines",
        "routine-split",
        "hourly",
        "library",
    ]
    hidden = validate_settings({"charts": []})
    assert hidden["charts"] == []
    subset = validate_settings(
        {
            "charts": [
                {"id": "hourly", "cols": 9, "height": 12},
                {"id": "nope"},
                {"id": "hourly"},
                {"id": "mix", "cols": "2", "height": "300"},
            ]
        }
    )
    assert [item["id"] for item in subset["charts"]] == ["hourly", "mix"]
    assert subset["charts"][0] == {"id": "hourly", "x": 0, "y": 0, "w": 24, "h": 20}
    assert subset["charts"][1] == {"id": "mix", "x": 0, "y": 20, "w": 16, "h": 38}
    saved = update_settings({"charts": [{"id": "top"}]})
    assert saved["charts"] == [{"id": "top", "x": 0, "y": 0, "w": 8, "h": 34}]
    public = public_settings()
    assert public["charts"] == [{"id": "top", "x": 0, "y": 0, "w": 8, "h": 34}]
    board = update_settings(
        {
            "charts": [
                {"id": "mix", "x": 0, "y": 0, "w": 4, "h": 24},
                {"id": "versus", "x": 4, "y": 0, "w": 6, "h": 50},
            ]
        }
    )
    assert board["charts"][0]["h"] == 24
    assert board["charts"][1]["h"] == 50
    assert board["charts"][1]["w"] == 6
