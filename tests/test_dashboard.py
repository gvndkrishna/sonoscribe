import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from sonoscribe.catalog import empty_library
from sonoscribe.dashboard.server import DashboardServer, static_dir
from sonoscribe.stats import StatsStore


@pytest.fixture(autouse=True)
def skip_hub_lookup(monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.transcriber.model_is_cached", lambda key: key == "large-v3-turbo")


def test_static_assets_exist() -> None:
    root = static_dir()
    assert (root / "index.html").is_file()
    assert (root / "styles.css").is_file()
    assert (root / "app.js").is_file()
    js = (root / "app.js").read_text(encoding="utf-8")
    assert "2 * 60 * 1000" in js
    assert "STATS_MS = 5000" in js
    assert "startAutoRefresh" in js
    assert "refreshStats" in js
    assert "sync-now" in js
    assert "sync-layout" in js
    assert "sync-toggle" in js
    assert "stats-device" in js
    assert "is-error" in js
    assert "renderVersus" in js
    assert "renderTypeSplit" in js
    assert "is-recording" in js
    assert "sync-chips" in js
    assert "needs_key" in js
    assert "needs_create" in js
    assert "/api/sync/join" in js
    assert "sync-username" in js
    assert "sync-private-key" in js
    assert "Add a username in Account" not in js
    assert "sync-edit" in js
    assert "sync-save" in js
    assert "/api/sync/validate" in js
    assert "/api/sync/sign-in" in js
    assert "sync-sign-in" in js
    assert "applySettingsAttention" in js
    assert "sync-facts" in js
    assert "sync-object" in js
    assert "works-in-query" in js
    assert "device-select" in js
    assert "All devices" in js
    assert "app-icon" in js
    assert "/api/apps/icon" in js
    assert "Works in" in js
    assert "has-tip" in js
    assert "launch-app-query" in js
    assert "launch-app-suggest" in js
    assert "/api/keys/record/start" in js
    assert "nativeKeyCapture" in js
    assert "/api/model" in js
    assert "model-builtin" in js
    assert "model-custom" in js
    assert "/api/model/test" in js
    assert "model-test" in js
    assert "custom-model-name" in js
    assert 'item.cached ? "cached"' not in js
    assert "item.hint" in js
    assert "/api/model/custom" in js
    assert "chart-resize-e" in js
    assert "chart-resize-s" in js
    assert "data-remove-chart" in js
    assert "add-chart" in js
    html = (root / "index.html").read_text(encoding="utf-8")
    assert (root / "favicon.svg").is_file()
    assert (root / "favicon.png").is_file()
    assert 'rel="icon"' in html
    assert "open-settings" in html
    assert 'id="settings"' in html
    assert 'id="stats-device"' in html
    assert 'id="account-username"' in html
    assert 'id="refresh-stats"' in html
    assert 'id="usage-grid"' in html
    assert 'id="stat-devices-wrap"' in html
    assert 'id="instrument-scope"' in html
    assert 'settings-mark' in html
    assert 'aria-label="Refresh stats"' in html
    assert 'aria-label="Add graph"' in html
    assert 'aria-label="Add command"' in html
    assert 'id="chart-grid"' in html
    assert 'id="add-chart"' in html
    assert 'id="chart-add-menu"' in html
    assert 'id="custom-model-path"' in html
    assert 'id="custom-model-name"' in html
    assert 'id="model-test"' in html
    assert 'id="model-builtin"' in html
    assert 'id="model-custom"' in html
    assert 'id="account-device-serial"' in html
    assert 'data-settings-pane="model"' in html
    assert 'id="pane-model"' in html
    assert "readonly" in html
    assert "02 / library" in html
    assert "03 / sequences" in html
    css = (root / "styles.css").read_text(encoding="utf-8")
    assert "#theme-picks" in css
    assert "[data-theme=\"dark\"] .instrument" in css
    assert "--meter-bg" in css
    assert "usage-grid" in css
    assert "usage-cell" in css
    assert "rec-pulse" in css
    assert "sync-facts" in css
    assert "sync-card-head" in css
    assert "sync-id-fields" in css
    assert "app-chip" in css
    assert "works-in-suggest" in css
    assert "has-tip" in css
    assert "model-picks" in css
    assert "model-stack" in css
    assert "model-add-form" in css
    assert "model-test-meta" in css
    assert "chart-resize" in css
    assert "chart-add-menu" in css
    assert "--canvas: #e4e4ea" in css
    assert "--panel: #ececf1" in css
    assert "--panel: #ffffff" not in css
    assert "--status-on" in css
    assert "--accent-glow" in css
    assert "--light-core" in css
    assert "--light-wash" in css
    assert ".masthead::before" not in css
    assert ".masthead::after" not in css
    assert "--mast: 48px" in css
    assert ".sync-dot.off" in css
    assert "settings-mark" in css
    assert "page-in" in css
    assert ".glass-fill" in css
    assert ".glass-box" in css
    assert ".glass-down" in css
    assert "--glass-bleed: 36px" in css
    assert "backdrop-filter" in css
    assert 'class="masthead glass glass-down"' in html
    assert "hold <kbd>fn</kbd> to dictate" not in html
    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)" in css
    assert 'data-view="overview"' in html
    assert "nav button svg" in css
    assert "nav button:hover span" in css
    assert "flex: 0 0 44px" in css
    assert "width: 4px" in css
    assert "pulseNav" in js
    assert "@keyframes nav-wave" in css
    assert "open-settings" in html
    assert 'id="open-settings"' in html
    assert "classList.add(\"is-open\")" in js
    assert 'class="glass-fill"' in html
    assert 'id="settings" class="glass glass-box"' in html
    assert 'id="editor" class="glass glass-box"' in html
    assert "glass-copy" in html
    assert 'id="toast"' in html
    assert 'id="toast-kicker"' in html
    assert 'popover="manual"' in html
    assert "placeToast" in js
    assert "in-overlay" in js
    assert "toast-up" in css
    assert "toast-down" in css
    assert "html[data-reduce-motion=\"true\"] #toast.is-on" in css
    assert 'id="chart-add-items"' in html
    assert "fill-arc" in css
    assert "meter-fill" in css
    assert "notice-row" in css
    assert '["blue", "purple", "amber", "teal", "gray"]' in js
    assert "OVERVIEW_ANIM_MS" in js
    assert "playOverviewMotion" in js
    assert "renderUsage" in js
    assert "glass-copy" in js
    assert "chart-add-items" in js
    assert "reduce-motion" in html
    assert 'id="reduce-motion"' in html
    assert 'id="private-mode"' in html
    assert "private_mode" in js
    assert 'id="dashboard-lock"' in html
    assert 'id="lock-gate"' in html
    assert "setLockScroll" in js
    assert "setPageFreeze" in js
    assert "packCharts" in js
    assert "edgeScroll" in js
    assert "html.is-locked" in css
    assert "html.is-frozen" in css
    assert "html.is-locked .shell" in css
    assert "#lock-gate:not([open])" in css
    assert "#lock-gate.lock-full[open]" in css
    assert 'id="reveal-commands"' in html
    assert 'id="reveal-routines"' in html
    assert 'id="lock-timeout"' in html
    assert 'id="lock-save"' in html
    assert 'id="lock-now"' in html
    assert 'id="lock-change"' in html
    assert 'id="lock-pin-fields"' in html
    assert 'id="lock-change-fields"' in html
    assert 'id="lock-pin-old"' in html
    assert 'id="lock-pin-new"' in html
    assert 'id="lock-pin-confirm"' in html
    assert 'id="lock-cancel-change"' in html
    assert "/api/lock/unlock" in js
    assert "/api/lock/confirm" in js
    assert "Touch ID" not in html
    assert "unlock-touch" not in js
    assert 'data-view="voice"' in html
    assert ">vocab</span>" in html
    assert "<h1>vocab</h1>" in html
    assert 'id="view-voice"' in html
    assert 'id="add-voice"' in html
    assert 'id="reveal-voice"' in html
    assert 'data-filter="text"' in html
    assert 'text: "Text"' in js
    assert "openVoiceEditor" in js
    assert "variables" in js
    assert "lockSaveVisible" in js
    assert "lockNowVisible" in js
    assert "syncReady" in js
    assert "showSettings" in js
    assert "sync-setup" in js
    assert "sync-interval" in js
    assert "syncWizard" in js
    assert 'data-settings-pane="sync"' in html
    assert 'aria-disabled="true"' in html
    assert "If this copy already has a name" in js


def test_library_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(tmp_path / "library.json"))
    monkeypatch.setenv("SONOSCRIBE_ROUTINES", str(tmp_path / "no-legacy.json"))
    stats = StatsStore(tmp_path / "stats.json")
    server = DashboardServer(stats, port=0)
    server.start()
    try:
        with urlopen(server.url + "api/library") as response:
            data = json.loads(response.read())
        assert any(item["id"] == "kbd-enter" for item in data["commands"])
        payload = empty_library()
        payload["commands"] = [
            item for item in payload["commands"] if item["type"] == "keyboard"
        ]
        payload["commands"].append(
            {
                "type": "website",
                "name": "Example",
                "phrases": ["example site"],
                "url": "https://example.com",
                "apps": [{"bundle_id": "com.apple.Safari", "name": "Safari"}],
            }
        )
        request = Request(
            server.url + "api/library",
            data=json.dumps(payload).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            saved = json.loads(response.read())
        assert any(item.get("url") == "https://example.com" for item in saved["commands"])
        example = next(item for item in saved["commands"] if item.get("url") == "https://example.com")
        assert example["apps"] == [{"bundle_id": "com.apple.Safari", "name": "Safari"}]
        payload["variables"] = [{"name": "hello", "value": "Greetings guys"}]
        payload["commands"].append(
            {
                "type": "text",
                "name": "Insert hello",
                "phrases": ["insert {hello}"],
                "text": "{hello}",
            }
        )
        request = Request(
            server.url + "api/library",
            data=json.dumps(payload).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            saved = json.loads(response.read())
        assert saved["variables"][0]["name"] == "hello"
        assert any(item.get("type") == "text" for item in saved["commands"])
        with urlopen(server.url) as response:
            html = response.read().decode()
        assert "Sonoscribe" in html
        assert "command-search" in html
        assert "activity-search" in html
        assert 'id="chart-grid"' in html
        assert 'id="add-chart"' in html
        with urlopen(server.url + "api/stats") as response:
            stats = json.loads(response.read())
        assert "charts" in stats
        assert "by_kind" in stats["charts"]
        assert "versus" in stats["charts"]
        assert "by_command_type" in stats["charts"]
        assert "by_model" in stats["charts"]
        assert "top_routines" in stats["charts"]
        assert "usage" in stats["charts"]
        assert len(stats["charts"]["usage"]) == 112
        with urlopen(server.url + "api/apps") as response:
            apps = json.loads(response.read())
        assert isinstance(apps["apps"], list)
        try:
            urlopen(server.url + "api/apps/icon?id=dev.sonoscribe.missing")
            raise AssertionError("expected 404")
        except HTTPError as exc:
            assert exc.code == 404
        with urlopen(server.url + "api/account") as response:
            account = json.loads(response.read())
        assert "username" in account
        assert account["device"]["id"]
        request = Request(
            server.url + "api/account",
            data=json.dumps({"username": "studio", "device": {"name": "Desk"}}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            saved_account = json.loads(response.read())
        assert saved_account["username"] == "studio"
        assert saved_account["device"]["name"] == "Desk"
        assert saved_account["private_mode"] is False
        request = Request(
            server.url + "api/account",
            data=json.dumps({"private_mode": True}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            private_account = json.loads(response.read())
        assert private_account["private_mode"] is True
        with urlopen(server.url + "api/settings") as response:
            private_prefs = json.loads(response.read())
        assert private_prefs["private_mode"] is True
        original_id = saved_account["device"]["id"]
        original_serial = saved_account["device"]["serial"]
        assert original_id
        assert original_serial
        request = Request(
            server.url + "api/account",
            data=json.dumps(
                {"device": {"id": "hacked-id", "serial": "HACKSERIAL", "name": "Desk"}}
            ).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            locked = json.loads(response.read())
        assert locked["device"]["id"] == original_id
        assert locked["device"]["serial"] == original_serial
        assert locked["device"]["name"] == "Desk"
        with urlopen(server.url + "api/settings") as response:
            prefs = json.loads(response.read())
        assert prefs["theme"] == "light"
        assert prefs["reduce_motion"] is False
        assert prefs["private_mode"] is True
        assert prefs["sync"]["interval_sec"] == 900
        assert prefs["sync_intervals"] == [0, 300, 900, 1800, 3600]
        request = Request(
            server.url + "api/settings",
            data=json.dumps({"sync": {"interval_sec": 300}}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            interval_prefs = json.loads(response.read())
        assert interval_prefs["sync"]["interval_sec"] == 300
        assert prefs["model"] == "large-v3-turbo"
        assert any(item["id"] == "small" for item in prefs["models"])
        assert prefs["accents"] == ["blue", "purple", "amber", "teal", "gray"]
        assert [item["id"] for item in prefs["charts"]][:3] == ["mix", "versus", "types"]
        library = next(item for item in prefs["charts"] if item["id"] == "library")
        assert library["w"] == 16
        assert library["x"] == 8
        mix = next(item for item in prefs["charts"] if item["id"] == "mix")
        versus = next(item for item in prefs["charts"] if item["id"] == "versus")
        assert mix["x"] == 0
        assert versus["x"] == 8
        assert mix["w"] == versus["w"] == 8
        request = Request(
            server.url + "api/settings",
            data=json.dumps(
                {"charts": [{"id": "daily", "cols": 2, "height": 280}, {"id": "mix"}]}
            ).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            chart_prefs = json.loads(response.read())
        assert [item["id"] for item in chart_prefs["charts"]] == ["daily", "mix"]
        assert chart_prefs["charts"][0]["w"] == 16
        assert chart_prefs["charts"][0]["h"] == 35
        assert chart_prefs["charts"][1]["x"] == 16
        request = Request(
            server.url + "api/settings",
            data=json.dumps({"theme": "dark", "accent": "teal"}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            saved_prefs = json.loads(response.read())
        assert saved_prefs["theme"] == "dark"
        assert saved_prefs["accent"] == "teal"
        assert [item["id"] for item in saved_prefs["charts"]] == ["daily", "mix"]
        request = Request(
            server.url + "api/settings",
            data=json.dumps({"reduce_motion": True}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            motion_prefs = json.loads(response.read())
        assert motion_prefs["reduce_motion"] is True
        with urlopen(server.url + "api/model") as response:
            model = json.loads(response.read())
        assert model["model"] == "large-v3-turbo"
        assert model["status"] == "ready"
        assert {item["id"] for item in model["models"]} == {"large-v3-turbo", "small", "base"}
        hints = {item["id"]: item["hint"] for item in model["models"]}
        assert hints == {"large-v3-turbo": "high", "small": "balanced", "base": "fast"}
        request = Request(
            server.url + "api/model",
            data=json.dumps({"model": "small"}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            switched = json.loads(response.read())
        assert switched["model"] == "small"
        request = Request(
            server.url + "api/model",
            data=json.dumps({"model": "nope"}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        try:
            urlopen(request)
            raise AssertionError("expected 400")
        except HTTPError as exc:
            assert exc.code == 400
        with urlopen(server.url + "api/sync/status") as response:
            sync = json.loads(response.read())
        assert "providers" in sync
        assert "private_key" not in sync
    finally:
        server.stop()


def test_sync_validate_rejects_empty_bucket(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(tmp_path / "library.json"))
    monkeypatch.setenv("SONOSCRIBE_ROUTINES", str(tmp_path / "no-legacy.json"))
    stats = StatsStore(tmp_path / "stats.json")
    server = DashboardServer(stats, port=0)
    server.start()
    try:
        request = Request(
            server.url + "api/sync/validate",
            data=json.dumps({"provider": "aws", "bucket": ""}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urlopen(request)
            raise AssertionError("expected 400")
        except HTTPError as exc:
            assert exc.code == 400
            body = json.loads(exc.read())
            assert "bucket" in body["error"].lower()
    finally:
        server.stop()


def test_key_record_without_native_tap(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(tmp_path / "library.json"))
    monkeypatch.setenv("SONOSCRIBE_ROUTINES", str(tmp_path / "no-legacy.json"))
    stats = StatsStore(tmp_path / "stats.json")
    server = DashboardServer(stats, port=0)
    server.start()
    try:
        request = Request(
            server.url + "api/keys/record/start",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            started = json.loads(response.read())
        assert started["native"] is False
        with urlopen(server.url + "api/keys/record/events") as response:
            events = json.loads(response.read())
        assert events["keys"] == []
        assert events["native"] is False
    finally:
        server.stop()


def test_model_put_notifies_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(tmp_path / "library.json"))
    seen: list[str] = []

    def set_model(key: str) -> dict:
        seen.append(key)
        return {"model": key, "active": "base", "status": "loading", "error": ""}

    stats = StatsStore(tmp_path / "stats.json")
    server = DashboardServer(
        stats,
        port=0,
        set_model=set_model,
        model_status=lambda: {"model": seen[-1] if seen else "base", "active": "base", "status": "loading", "error": ""},
    )
    server.start()
    try:
        request = Request(
            server.url + "api/model",
            data=json.dumps({"model": "small"}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            data = json.loads(response.read())
        assert seen == ["small"]
        assert data["model"] == "small"
        assert data["status"] == "loading"
        assert data["active"] == "base"
    finally:
        server.stop()


def test_custom_model_api_adds_local_folder(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(tmp_path / "library.json"))
    folder = tmp_path / "mlx-whisper"
    folder.mkdir()
    (folder / "config.json").write_text("{}", encoding="utf-8")
    (folder / "weights.npz").write_bytes(b"x")
    stats = StatsStore(tmp_path / "stats.json")
    server = DashboardServer(stats, port=0)
    server.start()
    try:
        request = Request(
            server.url + "api/model/custom",
            data=json.dumps({"path": str(folder), "name": "Desk"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            data = json.loads(response.read())
        assert any(item.get("custom") and item.get("label") == "Desk" for item in data["models"])
        desk = next(item for item in data["models"] if item.get("label") == "Desk")
        assert desk["hint"] == "custom"
        with urlopen(server.url + "api/model/test") as response:
            trial = json.loads(response.read())
        assert trial["listen"] is False
        assert trial["text"] == ""
        request = Request(
            server.url + "api/model/test",
            data=json.dumps({"listen": True}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            listening = json.loads(response.read())
        assert listening["listen"] is True
        assert server.append_test("hello there") is True
        with urlopen(server.url + "api/model/test") as response:
            heard = json.loads(response.read())
        assert heard["text"] == "hello there"
        request = Request(
            server.url + "api/model/test",
            data=json.dumps({"clear": True}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            cleared = json.loads(response.read())
        assert cleared["text"] == ""
        request = Request(
            server.url + "api/model/custom",
            data=json.dumps({"path": str(tmp_path / "missing")}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urlopen(request)
            raise AssertionError("expected 400")
        except HTTPError as exc:
            assert exc.code == 400
    finally:
        server.stop()


def test_sync_sign_in_route(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_LIBRARY", str(tmp_path / "library.json"))
    monkeypatch.setenv("SONOSCRIBE_SETTINGS", str(tmp_path / "settings.json"))
    from sonoscribe.settings import clear_settings_cache, update_settings

    clear_settings_cache()
    update_settings({"sync": {"provider": "gcs", "bucket": "demo"}})
    seen: list[list[str]] = []
    monkeypatch.setattr("sonoscribe.sync.service.open_login_terminal", lambda cmd: seen.append(list(cmd)))
    stats = StatsStore(tmp_path / "stats.json")
    server = DashboardServer(stats, port=0)
    server.start()
    try:
        request = Request(
            server.url + "api/sync/sign-in",
            data=json.dumps({}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            data = json.loads(response.read())
        assert data["ok"] is True
        assert data["command"] == "gcloud auth login"
        assert seen == [["gcloud", "auth", "login"]]
    finally:
        server.stop()
        clear_settings_cache()
