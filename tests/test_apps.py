import plistlib

from sonoscribe.apps import (
    app_icon_png,
    app_scope_ids,
    clean_apps,
    item_on_apps,
    pick_result,
    read_app,
    scopes_overlap,
)


def test_read_app_uses_info_plist(tmp_path) -> None:
    app = tmp_path / "Demo.app" / "Contents"
    app.mkdir(parents=True)
    (app / "Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleDisplayName": "Demo App",
                "CFBundleIdentifier": "dev.sonoscribe.demo",
            }
        )
    )
    info = read_app(app.parent)
    assert info["name"] == "Demo App"
    assert info["bundle_id"] == "dev.sonoscribe.demo"
    assert info["path"].endswith("Demo.app")


def test_pick_result_requires_something() -> None:
    assert pick_result({}) is None
    assert pick_result({"name": "Safari", "bundle_id": "com.apple.Safari"}) == {
        "name": "Safari",
        "bundle_id": "com.apple.Safari",
        "path": "",
    }


def test_clean_apps_dedupes_and_caps() -> None:
    cleaned = clean_apps(
        [
            {"bundle_id": "com.apple.Safari", "name": "Safari"},
            {"bundle_id": "com.apple.Safari", "name": "Safari 2"},
            "com.google.Chrome",
            {"name": "Notes"},
        ]
    )
    assert cleaned[0] == {"bundle_id": "com.apple.Safari", "name": "Safari"}
    assert cleaned[1]["bundle_id"] == "com.google.Chrome"
    assert cleaned[2] == {"bundle_id": "", "name": "Notes"}


def test_scopes_overlap_globals_and_sets() -> None:
    safari = app_scope_ids({"apps": [{"bundle_id": "com.apple.Safari"}]})
    chrome = app_scope_ids({"apps": [{"bundle_id": "com.google.Chrome"}]})
    both = app_scope_ids(
        {"apps": [{"bundle_id": "com.apple.Safari"}, {"bundle_id": "com.google.Chrome"}]}
    )
    empty = app_scope_ids({"apps": []})
    assert scopes_overlap(empty, empty) is True
    assert scopes_overlap(empty, safari) is False
    assert scopes_overlap(safari, chrome) is False
    assert scopes_overlap(safari, both) is True


def test_item_on_apps_matches_bundle_or_name() -> None:
    item = {"apps": [{"bundle_id": "com.apple.Safari", "name": "Safari"}]}
    assert item_on_apps(item, {"bundle_id": "com.apple.Safari", "name": "Safari"}) is True
    assert item_on_apps(item, {"bundle_id": "com.google.Chrome", "name": "Chrome"}) is False
    assert item_on_apps({"apps": []}, {"bundle_id": "com.apple.Safari"}) is True
    named = {"apps": [{"bundle_id": "", "name": "Safari"}]}
    assert item_on_apps(named, {"bundle_id": "", "name": "Safari"}) is True


def test_missing_icon_returns_none() -> None:
    assert app_icon_png("") is None
    assert app_icon_png("dev.sonoscribe.missing-app") is None
