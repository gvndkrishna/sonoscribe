from sonoscribe.device import is_this_device_only, item_on_device
from sonoscribe.sync.merge import apply_payload, merge_payloads, outgoing_library, parse_plain


def _cmd(item_id: str, devices: list[str], updated_at: str = "2026-01-01T00:00:00+00:00") -> dict:
    return {
        "id": item_id,
        "type": "keyboard",
        "name": item_id,
        "phrases": [item_id],
        "action": "enter",
        "devices": devices,
        "updated_at": updated_at,
    }


def test_this_device_only_is_not_uploaded() -> None:
    local = [_cmd("local-only", ["dev-a"]), _cmd("shared", [])]
    outgoing = outgoing_library(local, "dev-a")
    assert [item["id"] for item in outgoing] == ["shared"]
    assert is_this_device_only(local[0], "dev-a")
    assert not item_on_device(_cmd("other", ["dev-b"]), "dev-a")


def test_secret_items_are_not_uploaded_or_applied() -> None:
    local = [_cmd("hidden", []), _cmd("shared", [])]
    local[0]["secret"] = True
    outgoing = outgoing_library(local, "dev-a")
    assert [item["id"] for item in outgoing] == ["shared"]
    remote = {
        "username": "",
        "commands": [_cmd("leaked", []), _cmd("from-cloud", [])],
        "routines": [],
        "stats": {},
    }
    remote["commands"][0]["secret"] = True
    merged = merge_payloads(
        local={"commands": local, "routines": [], "username": "", "devices": [], "stats": {}},
        remote=remote,
        this_id="dev-a",
        what={"profile": True, "library": True, "stats": False},
    )
    ids = {item["id"] for item in merged["commands"]}
    assert "hidden" in ids
    assert "from-cloud" in ids
    assert "leaked" not in ids
    applied = apply_payload(
        local_library={"commands": local, "routines": []},
        remote=remote,
        this_id="dev-a",
        what={"library": True, "profile": False, "stats": False},
    )
    applied_ids = {item["id"] for item in applied["library"]["commands"]}
    assert "hidden" in applied_ids
    assert "leaked" not in applied_ids
    local_vars = [{"id": "var-hidden", "name": "hush", "value": "quiet", "secret": True}]
    remote["variables"] = [
        {"id": "var-leaked", "name": "leak", "value": "nope", "secret": True},
        {"id": "var-shared", "name": "hello", "value": "hi"},
    ]
    outgoing_vars = outgoing_library(local_vars + [{"id": "var-shared", "name": "hello", "value": "hi"}], "dev-a")
    assert [item["id"] for item in outgoing_vars] == ["var-shared"]
    merged = merge_payloads(
        local={"commands": [], "routines": [], "variables": local_vars, "username": "", "devices": [], "stats": {}},
        remote=remote,
        this_id="dev-a",
        what={"profile": True, "library": True, "stats": False},
    )
    var_ids = {item["id"] for item in merged["variables"]}
    assert "var-hidden" in var_ids
    assert "var-shared" in var_ids
    assert "var-leaked" not in var_ids


def test_parse_v1_library_payload() -> None:
    parsed = parse_plain({"commands": [_cmd("kbd-enter", [])], "routines": []})
    assert parsed["v"] == 2
    assert parsed["commands"][0]["id"] == "kbd-enter"
    assert parsed["username"] == ""


def test_merge_keeps_local_only_and_takes_shared_remote() -> None:
    local = {
        "username": "studio",
        "username_updated_at": "2026-02-01T00:00:00+00:00",
        "devices": [{"id": "dev-a", "name": "A", "updated_at": "2026-02-01T00:00:00+00:00"}],
        "commands": [_cmd("local-only", ["dev-a"]), _cmd("shared", [], "2026-01-01T00:00:00+00:00")],
        "routines": [],
        "stats": {},
    }
    remote = {
        "username": "other",
        "username_updated_at": "2026-01-01T00:00:00+00:00",
        "devices": [{"id": "dev-b", "name": "B", "updated_at": "2026-02-02T00:00:00+00:00"}],
        "commands": [_cmd("shared", [], "2026-03-01T00:00:00+00:00"), _cmd("from-b", ["dev-b"])],
        "routines": [],
        "stats": {"dev-b": {"command_runs": 4, "activity": []}},
    }
    merged = merge_payloads(
        local=local,
        remote=remote,
        this_id="dev-a",
        what={"profile": True, "library": True, "stats": True},
    )
    assert merged["username"] == "studio"
    ids = {item["id"] for item in merged["commands"]}
    assert ids == {"local-only", "shared", "from-b"}
    shared = next(item for item in merged["commands"] if item["id"] == "shared")
    assert shared["updated_at"].startswith("2026-03-01")
    assert {item["id"] for item in merged["devices"]} >= {"dev-a", "dev-b"}
    upload = outgoing_library(merged["commands"], "dev-a")
    assert "local-only" not in {item["id"] for item in upload}


def test_merge_drops_generated_alias_and_combines_stats() -> None:
    local = {
        "username": "studio",
        "username_updated_at": "2026-02-01T00:00:00+00:00",
        "devices": [
            {
                "id": "C02SERIAL01",
                "serial": "C02SERIAL01",
                "name": "H7T46T609N",
                "previous_ids": ["dev-99b7193939a6"],
                "updated_at": "2026-02-01T00:00:00+00:00",
            }
        ],
        "commands": [],
        "routines": [],
        "stats": {
            "C02SERIAL01": {
                "command_runs": 2,
                "activity": [{"at": "2026-02-01T00:00:00+00:00", "kind": "command", "label": "Save"}],
            }
        },
    }
    remote = {
        "username": "studio",
        "username_updated_at": "2026-01-01T00:00:00+00:00",
        "devices": [
            {"id": "dev-99b7193939a6", "serial": "dev-99b7193939a6", "name": "H7T46T609N"},
            {"id": "dev-b", "name": "B"},
        ],
        "commands": [_cmd("from-old", ["dev-99b7193939a6"])],
        "routines": [],
        "stats": {
            "dev-99b7193939a6": {
                "command_runs": 9,
                "activity": [{"at": "2026-01-01T00:00:00+00:00", "kind": "command", "label": "Mute"}],
            }
        },
    }
    merged = merge_payloads(
        local=local,
        remote=remote,
        this_id="C02SERIAL01",
        what={"profile": True, "library": True, "stats": True},
    )
    ids = {item["id"] for item in merged["devices"]}
    assert "C02SERIAL01" in ids
    assert "dev-99b7193939a6" not in ids
    assert "dev-b" in ids
    assert merged["stats"]["C02SERIAL01"]["command_runs"] == 9
    assert "dev-99b7193939a6" not in merged["stats"]
    assigned = next(item for item in merged["commands"] if item["id"] == "from-old")
    assert assigned["devices"] == ["C02SERIAL01"]


def test_apply_keeps_this_device_only() -> None:
    local_library = {"commands": [_cmd("local-only", ["dev-a"])], "routines": []}
    remote = {"commands": [_cmd("shared", [])], "routines": []}
    applied = apply_payload(
        local_library=local_library,
        remote=remote,
        this_id="dev-a",
        what={"profile": True, "library": True, "stats": False},
    )
    ids = {item["id"] for item in applied["library"]["commands"]}
    assert ids == {"local-only", "shared"}


def test_merge_keeps_newer_voice_variable() -> None:
    local = {
        "username": "studio",
        "username_updated_at": "2026-02-01T00:00:00+00:00",
        "devices": [{"id": "dev-a", "name": "A"}],
        "commands": [],
        "routines": [],
        "variables": [
            {
                "id": "var-hello",
                "name": "hello",
                "value": "old",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ],
        "stats": {},
    }
    remote = {
        "username": "studio",
        "username_updated_at": "2026-01-01T00:00:00+00:00",
        "devices": [{"id": "dev-b", "name": "B"}],
        "commands": [],
        "routines": [],
        "variables": [
            {
                "id": "var-hello",
                "name": "hello",
                "value": "Greetings guys",
                "updated_at": "2026-03-01T00:00:00+00:00",
            },
            {
                "id": "var-bye",
                "name": "bye",
                "value": "later",
                "updated_at": "2026-03-01T00:00:00+00:00",
            },
        ],
        "stats": {},
    }
    merged = merge_payloads(
        local=local,
        remote=remote,
        this_id="dev-a",
        what={"profile": True, "library": True, "stats": False},
    )
    by_id = {item["id"]: item for item in merged["variables"]}
    assert by_id["var-hello"]["value"] == "Greetings guys"
    assert "var-bye" in by_id
