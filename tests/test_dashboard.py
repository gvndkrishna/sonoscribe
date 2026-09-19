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
    assert "PRESENCE_MS" in js
    assert "startPresence" in js
    assert "refreshView" in js
    assert "/api/presence" in js
    assert "refreshStats" in js
    assert 'currentView() === "overview"' in js
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
    assert "openPlayground" in js
    assert "consumePlaygroundScroll" in js
    assert "playgroundSettledAtTop" in js
    assert "command mode off" in js
    assert "_skipLock" in js
    assert "const PAGE_SIZE = 30" in js
    assert "fillPager" in js
    assert "data-pager" in js
    assert "activityItems = stats.activity || []" in js
    assert "findQuery" in js
    assert "findElseHtml" in js
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
    assert 'id="stat-scouts"' in html
    assert "stat-scouts" in js
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
    assert 'id="playground"' in html
    assert 'id="playground-text"' in html
    assert 'id="playground-kicker">playground' in html
    assert 'id="playground-cue"' in html
    assert 'id="activity-pager"' in html
    assert 'id="command-pager"' in html
    assert 'id="routine-pager"' in html
    assert 'id="voice-pager"' in html
    assert 'id="scout-pager"' in html
    assert 'id="scribe-pager"' in html
    assert 'id="view-scribe"' in html
    assert 'id="scribe-new"' in html
    assert 'class="scribe-field"' in html
    assert 'id="vocanote"' in html
    assert 'id="vocanote-repeat"' in html
    assert "dismissVocanote" in js
    assert "repeatLabel" in js
    assert 'data-view="scribe"' in html
    assert "06 / vocanotes" in html
    assert "/api/scribe" in js
    assert "refreshScribe" in js
    assert "bindScribe" in js
    assert "scribeDictateOpen" in js
    assert "data-scribe-delete" in js
    assert "bumpScribe" in js
    assert "scribeBusy" in js
    assert "scribeGone" in js
    assert "rememberScribeGone" in js
    assert "ss-scribe-gone" in js
    assert "delete payload.vocanotes" in js
    assert "scroll to open playground mode" in html
    assert 'id="model-builtin"' in html
    assert 'id="model-custom"' in html
    assert 'id="account-device-serial"' in html
    assert 'data-settings-pane="model"' in html
    assert 'id="pane-model"' in html
    assert "readonly" in html
    assert "02 / library" in html
    assert "03 / sequences" in html
    css = (root / "styles.css").read_text(encoding="utf-8")
    assert "#scribe-new" in css
    assert ".scribe-field" in css
    assert "grid-template-columns: 56px minmax(0, 1fr) auto" in css
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
    assert ".pager" in css
    assert "height: 25vh" in css
    assert "#playground" in css
    assert "html.is-playground" in css
    assert "--playground-shift" in css
    assert "margin-top: var(--playground-shift)" in css
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
    assert 'viewport-fit=cover' in html
    assert 'class="masthead glass glass-down"' in html
    assert "env(safe-area-inset-bottom" in css
    assert "hold <kbd>fn</kbd> to dictate" not in html
    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)" in css
    assert 'data-view="overview"' in html
    assert html.count('class="overview-footer glass glass-box"') == 1
    assert "Designed by Govind Krishna" in html
    assert html.index("overview-footer") < html.index('id="view-commands"')
    assert ".overview-footer:hover .overview-footer-credit" in css
    assert "nav button svg" in css
    assert "nav button:hover span" in css
    assert "flex: 0 0 44px" in css
    assert "width: 4px" in css
    assert "pulseNav" in js
    assert "pulsePress" in js
    assert "bindPressFeedback" in js
    assert "icon-plus" in html
    assert "@keyframes icon-refresh" in css
    assert "@keyframes btn-accent" in css
    assert 'id="wordmark-pulse"' in html
    assert "pulseWordmark" in js
    assert ".wordmark.is-press > span" in css
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
    assert 'id="lock-mark"' in html
    assert "lock-shackle" in html
    assert "@keyframes lock-open" in css
    assert "@keyframes lock-hint" not in css
    assert "playUnlockMark" in js
    assert "keepGate" in js
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
    assert "never" in js
    assert "no limit" in js
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
    assert "/api/lock/disable" in js
    assert 'promptLock("off")' in js
    assert "Touch ID" not in html
    assert "unlock-touch" not in js
    assert 'data-view="voice"' in html
    assert ">vocab</span>" in html
    assert "<h1>vocab</h1>" in html
    assert 'data-view="scout"' in html
    assert 'cx="12" cy="12" r="8"' in html
    assert 'id="view-scout"' in html
    assert "05 / briefs" in html
    assert 'id="pane-scout"' in html
    assert 'data-settings-pane="scout"' in html
    assert 'id="scout-settings"' in html
    assert 'id="scout-tools"' in html
    assert 'id="scout-context"' in html
    assert 'id="add-mcp"' in html
    assert 'id="scout-key"' in html
    assert 'id="scout-key-wrap"' in html
    assert 'id="change-scout-key"' in html
    assert 'id="cancel-scout-key"' in html
    assert 'id="brief"' in html
    assert 'id="select-commands"' in html
    assert 'id="delete-commands"' in html
    assert 'id="select-routines"' in html
    assert 'id="delete-routines"' in html
    assert 'id="select-voice"' in html
    assert 'id="delete-voice"' in html
    assert 'id="select-briefs"' in html
    assert 'id="delete-briefs"' in html
    assert "brief-preview" in js
    assert "scoutModelFor" in js
    assert "change api key" in html
    assert "/api/scout" in js
    assert "scout-tokens" in js
    assert "scout-cost" in js
    assert "scoutReady" in js
    assert "parseMcpEnv" in js
    assert 'id="mcp-env"' in html
    assert "location.hash" in js
    assert "openBrief" in js
    assert "briefSku" in js
    assert "sc–" in js
    assert "open_id" in js
    assert "open_page" in js
    assert "capture_screen" in js
    assert "setBriefContinue" in js
    assert "/api/scout/continue" in js
    assert "data.open_id" in js
    assert "say scout, then a follow-up" in html
    assert 'id="brief-hint"' in html
    assert 'id="brief-thread"' in html
    assert 'id="brief-cancel"' in html
    assert 'id="brief-insert"' in html
    assert "/api/scout/insert" in js
    assert "briefCanInsert" in js
    assert "insertOpenBrief" in js
    assert "brief-turn-insert" not in js
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
    assert "applyTabState" in js
    assert "claimThisTab" in js
    assert "busy ? 700 : 1100" in js
    assert 'id="tab-gate"' in html
    assert 'id="tab-claim"' in html


def test_latest_tab_owns_focus_and_scout_page(tmp_path) -> None:
    stats = StatsStore(tmp_path / "stats.json")
    server = DashboardServer(stats, port=0)
    assert server.scout_page_open() is False
    assert server.note_client(tab="a", view="scout", claim=True) == "ok"
    assert server.scout_page_open() is True
    assert server.note_client(tab="b", view="overview", claim=True) == "ok"
    assert server.scout_page_open() is False
    assert server.note_client(tab="a", view="scout") == "stale"
    server.request_focus("scout")
    server.request_open_brief("tsk-1")
    assert server.consume_focus("a") == ""
    assert server.peek_open_brief("a") == ""
    assert server.consume_focus("b") == "scout"
    assert server.consume_open_brief("b") == "tsk-1"
    assert server.presence_payload("tab=b&view=overview")["tab"] == "ok"
    stale = server.presence_payload("tab=a&view=scout")
    assert stale["tab"] == "stale"
    assert stale["focus"] == ""
    assert stale["open_id"] == ""
    assert server.note_client(tab="b", view="scribe", claim=True) == "ok"
    server.request_open_note("voc-1")
    assert server.peek_open_note("a") == ""
    assert server.consume_open_note("b") == "voc-1"


def test_scribe_api_create_edit_delete(tmp_path) -> None:
    stats = StatsStore(tmp_path / "stats.json")
    server = DashboardServer(stats, port=0)
    server.start()
    try:
        request = Request(
            server.url + "api/scribe",
            data=json.dumps({"text": "pay bills at 8 o'clock"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            created = json.loads(response.read())
        note = created["item"]
        assert note["is_todo"] is True
        assert note["is_reminder"] is True
        assert note["title"] == "pay bills at 8 o'clock"
        patch = Request(
            server.url + "api/scribe",
            data=json.dumps({"id": note["id"], "title": "pay the bills", "is_todo": True, "is_reminder": False}).encode(),
            method="PATCH",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(patch) as response:
            saved = json.loads(response.read())
        assert saved["item"]["title"] == "pay the bills"
        assert saved["item"]["is_reminder"] is False
        delete = Request(
            server.url + "api/scribe",
            data=json.dumps({"ids": [note["id"]]}).encode(),
            method="DELETE",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(delete) as response:
            gone = json.loads(response.read())
        assert gone["items"] == []
        stale = Request(
            server.url + "api/library",
            data=json.dumps(
                {
                    "commands": empty_library()["commands"],
                    "routines": [],
                    "variables": [],
                    "vocanotes": [note],
                }
            ).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(stale) as response:
            library = json.loads(response.read())
        assert all(item.get("id") != note["id"] for item in library.get("vocanotes") or [])
        with urlopen(server.url + "api/scribe") as response:
            listed = json.loads(response.read())
        assert listed["items"] == []
    finally:
        server.stop()


def test_test_listening_captures_dictation(tmp_path) -> None:
    stats = StatsStore(tmp_path / "stats.json")
    server = DashboardServer(stats, port=0)
    assert server.test_listening() is False
    assert server.append_test("hello") is False
    server.set_test({"listen": True})
    assert server.test_listening() is True
    assert server.append_test("hello") is True
    assert server.test_state()["text"] == "hello"
    server.set_test({"listen": False})
    assert server.test_listening() is False
    assert server.append_test("again") is False
    assert server.test_state()["text"] == "hello"
    server.set_test({"listen": True, "sink": "scribe", "clear": True})
    assert server.append_test("milk") is True
    state = server.test_state()
    assert state["sink"] == "scribe"
    assert state["text"] == "milk"


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
        assert "open-find" in html
        assert "find-query" in html
        assert "activity-search" in html
        assert "command-search" not in html
        assert "voice-search" not in html
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
        assert server.test_listening() is True
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


def test_scout_routes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SONOSCRIBE_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SONOSCRIBE_SCOUT", str(tmp_path / "scout.json"))
    from sonoscribe.settings import clear_settings_cache

    clear_settings_cache()
    stats = StatsStore(tmp_path / "stats.json")
    server = DashboardServer(stats, port=0)
    server.start()
    try:
        with urlopen(server.url + "api/scout") as response:
            data = json.loads(response.read())
        assert data["runs"] == []
        assert "focus" in data
        server.request_focus("scout")
        with urlopen(server.url + "api/presence") as response:
            presence = json.loads(response.read())
        assert presence["focus"] == "scout"
        assert server.client_open() is True
        with urlopen(server.url + "api/presence") as response:
            idle = json.loads(response.read())
        assert idle["focus"] == ""
        server.request_focus("scout")
        with urlopen(server.url + "api/scout") as response:
            focused = json.loads(response.read())
        assert focused["focus"] == "scout"
        assert server.client_open() is True
        assert focused.get("continue_id") == ""
        assert focused.get("open_id") == ""
        from sonoscribe.scout.store import upsert_run

        upsert_run(
            {
                "id": "tsk-dash",
                "prompt": "weather in chicago",
                "status": "done",
                "want_insert": True,
                "answer": {"kind": "qa", "title": "chicago weather", "blocks": [{"type": "lead", "text": "52"}]},
            },
            active=False,
        )
        with urlopen(server.url + "api/scout") as response:
            listed = json.loads(response.read())
        assert listed["runs"][0]["sku"] == "sc–01"
        assert listed["runs"][0]["n"] == 1
        from sonoscribe.scout import set_brief_insert

        pasted: list[dict] = []
        set_brief_insert(pasted.append)
        request = Request(
            server.url + "api/scout/insert",
            data=json.dumps({"id": "tsk-dash"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            inserted = json.loads(response.read())
        assert inserted["run"]["insert_text"] == "52"
        assert pasted[0]["id"] == "tsk-dash"
        server.request_open_brief("tsk-dash")
        with urlopen(server.url + "api/presence") as response:
            peek = json.loads(response.read())
        assert peek["open_id"] == "tsk-dash"
        assert peek["focus"] == "scout"
        with urlopen(server.url + "api/presence") as response:
            still = json.loads(response.read())
        assert still["open_id"] == "tsk-dash"
        with urlopen(server.url + "api/scout") as response:
            opened = json.loads(response.read())
        assert opened["open_id"] == "tsk-dash"
        assert opened["focus"] == ""
        with urlopen(server.url + "api/presence") as response:
            after = json.loads(response.read())
        assert after["open_id"] == ""
        request = Request(
            server.url + "api/scout/title",
            data=json.dumps({"id": "tsk-dash", "title": "lake wind"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            renamed = json.loads(response.read())
        assert renamed["run"]["title"] == "lake wind"
        request = Request(
            server.url + "api/scout/continue",
            data=json.dumps({"id": "tsk-dash"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            armed = json.loads(response.read())
        assert armed["continue_id"] == "tsk-dash"
        request = Request(
            server.url + "api/scout/continue",
            data=json.dumps({"id": ""}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            idle = json.loads(response.read())
        assert idle["continue_id"] == ""
        request = Request(
            server.url + "api/scout/delete",
            data=json.dumps({"ids": ["tsk-dash"]}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            deleted = json.loads(response.read())
        assert deleted["runs"] == []
        with urlopen(server.url + "api/scout/settings") as response:
            scout = json.loads(response.read())
        assert scout["provider"] == "openai"
        assert scout["has_key"] is False
        assert scout["lock_ok"] is False
        request = Request(
            server.url + "api/scout/settings",
            data=json.dumps({"provider": "anthropic", "model": "claude-sonnet-4-0"}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(HTTPError) as blocked:
            urlopen(request)
        assert blocked.value.code == 400
        from sonoscribe.settings import update_settings

        update_settings({"lock": {"enabled": True, "method": "pin"}})
        server.lock.require_unlocked = lambda token: None
        server.lock.require_confirm = lambda token: {}
        request = Request(
            server.url + "api/scout/settings",
            data=json.dumps({"provider": "anthropic", "model": "claude-sonnet-4-0"}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            saved = json.loads(response.read())
        assert saved["provider"] == "anthropic"
        assert saved["model"] == "claude-sonnet-4-0"
        assert saved["models"]["anthropic"] == "claude-sonnet-4-0"
        request = Request(
            server.url + "api/scout/key",
            data=json.dumps({"provider": "anthropic", "key": "sk-ant-test"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            keyed = json.loads(response.read())
        assert keyed["has_key"] is True
    finally:
        server.stop()
        clear_settings_cache()
