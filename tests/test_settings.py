from sonoscribe.settings import (
    SCOUT_DEFAULT_MODELS,
    empty_settings,
    load_settings,
    public_account,
    public_settings,
    public_scout,
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
    never = update_settings({"lock": {"timeout_sec": 0}})
    assert never["lock"]["timeout_sec"] == 0
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
    assert public["scout"]["provider"] == "openai"
    assert public["scout"]["has_key"] is False
    assert public["scout"]["lock_ok"] is False
    assert public["scout"]["tools"] == [
        "search",
        "weather",
        "fetch",
        "open_page",
        "run_script",
        "write_file",
        "read_file",
    ]
    assert "capture_screen" not in public["scout"]["tools"]
    assert public["scout"]["auto"] == ["search", "weather", "fetch", "open_page"]
    assert any(item["id"] == "weather" for item in public["scout"]["tool_catalog"])
    assert any(item["id"] == "capture_screen" for item in public["scout"]["tool_catalog"])
    assert all(item["id"] != "insert" for item in public["scout"]["tool_catalog"])
    assert "insert" not in public["scout"]["tools"]
    assert "key" not in public["scout"]
    assert public["scout"]["models"]["openai"] == SCOUT_DEFAULT_MODELS["openai"]
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
    extra = validate_settings({"charts": [{"id": "task-tokens"}, {"id": "task-cost"}]})
    assert [item["id"] for item in extra["charts"]] == ["scout-tokens", "scout-cost"]
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


def test_task_models_survive_provider_switch() -> None:
    custom = "us.anthropic.claude-sonnet-5-custom"
    update_settings({"scout": {"provider": "bedrock", "model": custom, "bedrock_region": "us-west-2"}})
    stored = load_settings()["scout"]
    assert stored["provider"] == "bedrock"
    assert stored["model"] == custom
    assert stored["bedrock_model"] == custom
    assert stored["models"]["bedrock"] == custom
    update_settings({"scout": {"provider": "anthropic"}})
    switched = load_settings()["scout"]
    assert switched["provider"] == "anthropic"
    assert switched["model"] == SCOUT_DEFAULT_MODELS["anthropic"]
    assert switched["models"]["bedrock"] == custom
    assert switched["bedrock_model"] == custom
    update_settings({"scout": {"provider": "bedrock"}})
    back = load_settings()["scout"]
    assert back["provider"] == "bedrock"
    assert back["model"] == custom
    assert back["bedrock_model"] == custom
    assert back["bedrock_region"] == "us-west-2"
    public = public_settings()["scout"]
    assert public["model"] == custom
    assert public["models"]["bedrock"] == custom


def test_task_legacy_fields_seed_models() -> None:
    cleaned = validate_settings(
        {
            "tasks": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-0",
                "bedrock_model": "us.anthropic.kept",
            }
        }
    )
    assert cleaned["scout"]["models"]["anthropic"] == "claude-sonnet-4-0"
    assert cleaned["scout"]["models"]["bedrock"] == "us.anthropic.kept"
    assert cleaned["scout"]["bedrock_model"] == "us.anthropic.kept"


def test_task_tools_context_and_limits_clean() -> None:
    cleaned = validate_settings(
        {
            "tasks": {
                "tools": ["search", "write_file", "nope"],
                "auto": ["write_file", "search", "fetch"],
                "context": "be terse",
                "max_tokens": 4000,
                "duration_sec": 30,
                "mcps": [{"id": "mcp-1", "name": "gh", "command": "npx", "transport": "stdio"}],
            }
        }
    )
    assert cleaned["scout"]["tools"] == ["search", "write_file"]
    assert cleaned["scout"]["auto"] == ["write_file", "search"]
    assert cleaned["scout"]["context"] == "be terse"
    assert cleaned["scout"]["max_tokens"] == 4000
    assert cleaned["scout"]["duration_sec"] == 30
    assert cleaned["scout"]["mcps"][0]["command"] == "npx"
    update_settings({"scout": cleaned["scout"]})
    saved = update_settings({"scout": {"auto": ["search"], "max_tokens": 16000}})
    assert saved["scout"]["auto"] == ["search"]
    assert saved["scout"]["max_tokens"] == 16000
    assert saved["scout"]["tools"] == ["search", "write_file"]
    none = update_settings({"scout": {"max_tokens": 0, "duration_sec": 0}})
    assert none["scout"]["max_tokens"] == 0
    assert none["scout"]["duration_sec"] == 0
    public = public_scout()
    assert public["max_tokens"] == 0
    assert public["duration_sec"] == 0
    assert public["token_limits"][0] == 0
    assert public["duration_limits"][0] == 0


def test_legacy_task_tools_gain_browser() -> None:
    cleaned = validate_settings(
        {"scout": {"tools": ["search", "fetch", "run_script", "write_file", "read_file"], "auto": ["search", "fetch"]}}
    )
    assert "open_page" in cleaned["scout"]["tools"]
    assert "open_page" in cleaned["scout"]["auto"]
    assert "weather" in cleaned["scout"]["tools"]
    assert "weather" in cleaned["scout"]["auto"]
    assert "capture_screen" not in cleaned["scout"]["tools"]


def test_old_tools_with_capture_gain_weather() -> None:
    cleaned = validate_settings(
        {
            "scout": {
                "tools": [
                    "search",
                    "fetch",
                    "open_page",
                    "run_script",
                    "write_file",
                    "read_file",
                    "capture_screen",
                ],
                "auto": ["search", "fetch", "open_page", "capture_screen"],
            }
        }
    )
    assert "weather" in cleaned["scout"]["tools"]
    assert "weather" in cleaned["scout"]["auto"]
    assert "capture_screen" in cleaned["scout"]["tools"]
    opted = validate_settings(
        {
            "scout": {
                "tools_version": 2,
                "tools": [
                    "search",
                    "fetch",
                    "open_page",
                    "run_script",
                    "write_file",
                    "read_file",
                    "capture_screen",
                ],
                "auto": ["search", "fetch", "open_page"],
            }
        }
    )
    assert "weather" not in opted["scout"]["tools"]


def test_capture_screen_is_opt_in() -> None:
    from sonoscribe.settings import SCOUT_TOOLS, empty_scout, validate_settings

    assert "capture_screen" not in empty_scout()["tools"]
    assert "capture_screen" not in SCOUT_TOOLS
    kept = validate_settings({"scout": {"tools": list(SCOUT_TOOLS) + ["capture_screen"]}})
    assert "capture_screen" in kept["scout"]["tools"]
    assert kept["scout"]["tools"][-1] == "capture_screen"


def test_mcp_env_is_kept_and_redacted() -> None:
    saved = update_settings(
        {
            "tasks": {
                "mcps": [
                    {
                        "id": "mcp-1",
                        "name": "gh",
                        "command": "npx",
                        "transport": "stdio",
                        "env": {"TOKEN": "secret"},
                    }
                ]
            }
        }
    )
    assert saved["scout"]["mcps"][0]["env"]["TOKEN"] == "secret"
    public = public_scout()
    assert "env" not in public["mcps"][0]
    assert public["mcps"][0]["has_env"] is True
    again = update_settings({"scout": {"mcps": [{**public["mcps"][0], "auto": True}]}})
    assert again["scout"]["mcps"][0]["env"]["TOKEN"] == "secret"
    assert again["scout"]["mcps"][0]["auto"] is True


def test_legacy_tasks_settings_load_as_scout() -> None:
    cleaned = validate_settings({"tasks": {"provider": "grok", "model": "grok-3"}})
    assert "tasks" not in cleaned
    assert cleaned["scout"]["provider"] == "grok"
    assert cleaned["scout"]["model"] == "grok-3"
    saved = update_settings({"tasks": {"provider": "kimi"}})
    assert "tasks" not in saved
    assert saved["scout"]["provider"] == "kimi"
