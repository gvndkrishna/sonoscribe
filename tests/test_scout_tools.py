import subprocess
from pathlib import Path

import pytest

from sonoscribe.scout.tools import (
    FETCH_LIMIT,
    SEARCH_HITS,
    ToolError,
    auto_tools,
    browser_target,
    capture_screen,
    confirm_preview,
    enabled_tools,
    fetch_url,
    host_blocked,
    needs_confirm,
    open_page,
    parse_search_html,
    resolve_home_path,
    run_tool,
    run_user_script,
    search,
    take_capture,
    video_intent,
)


def test_host_blocks_loopback() -> None:
    assert host_blocked("localhost") is True
    assert host_blocked("127.0.0.1") is True


def test_home_path_stays_under_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.scout.tools._HOME", tmp_path)
    inside = resolve_home_path(str(tmp_path / "notes.txt"))
    assert inside == (tmp_path / "notes.txt").resolve()
    with pytest.raises(ToolError):
        resolve_home_path("/etc/passwd")


def test_parse_search_html() -> None:
    html = """
    <a class="result__a" href="https://weather.gov/chicago">Chicago weather</a>
    <a class="result__snippet">52 and rain</a>
    """
    hits = parse_search_html(html)
    assert hits[0]["title"] == "Chicago weather"
    assert hits[0]["url"] == "https://weather.gov/chicago"
    assert "52" in hits[0]["snippet"]


def test_search_falls_back_to_wikipedia(monkeypatch) -> None:
    def fake_get(url, accept="text/plain, text/html", **_k):
        if "wikipedia.org" in url:
            return (
                '{"query":{"search":[{"title":"Asia",'
                '"snippet":"the <span class=\\"searchmatch\\">largest</span> continent"}]}}'
            )
        return "<html>anomaly.js?sv=html&cc=botnet</html>"

    monkeypatch.setattr("sonoscribe.scout.tools._http_get", fake_get)
    text = search("largest continent")
    assert text.startswith("untrusted web text:")
    assert "Asia" in text
    assert "wikipedia.org/wiki/Asia" in text
    assert "largest continent" in text


def test_search_miss_is_not_web_text(monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.scout.tools._http_get", lambda *a, **k: "<html></html>")
    text = search("zzzz-no-hits")
    assert "No live hits" in text
    assert "google.com/search" in text
    assert "bing.com/search" in text
    assert not text.startswith("untrusted web text:")


def test_script_rejects_sudo() -> None:
    with pytest.raises(ToolError):
        run_user_script("bash", "sudo rm -rf /")


def test_video_intent_skips_device_watch() -> None:
    assert video_intent("endgame trailer") is True
    assert video_intent("watch interstellar") is True
    assert video_intent("last of us on netflix") is True
    assert video_intent("avengers tickets") is False
    assert video_intent("apple watch price") is False


def test_browser_target_sends_video_to_official_platforms() -> None:
    assert "youtube.com/results" in browser_target("", "endgame trailer")
    assert "search_query=interstellar" in browser_target("watch interstellar")
    assert "netflix.com/search" in browser_target("", "last of us on netflix")
    assert "primevideo.com" in browser_target("", "reacher on prime video")
    assert browser_target("nasa.gov") == "https://nasa.gov"
    assert "google.com/search" in browser_target("", "avengers tickets")
    assert "google.com/search" in browser_target("", "apple watch price")
    assert browser_target("https://www.youtube.com/watch?v=abc") == "https://www.youtube.com/watch?v=abc"
    assert "youtube.com/results" in browser_target("youtube.com", "endgame")
    assert "youtube.com/results" in browser_target("https://www.youtube.com", "endgame")


def test_search_video_prefers_youtube(monkeypatch) -> None:
    seen: list[str] = []

    def fake_get(url, accept="text/plain, text/html", **_k):
        seen.append(url)
        return "<html></html>"

    monkeypatch.setattr("sonoscribe.scout.tools._http_get", fake_get)
    search("endgame trailer")
    assert any("youtube.com" in url for url in seen)
    seen.clear()
    search("largest continent")
    assert not any("youtube.com" in url for url in seen)


def test_open_page_queues_until_notice(monkeypatch) -> None:
    from sonoscribe.scout.tools import take_queued_page

    seen = []
    monkeypatch.setattr("sonoscribe.scout.tools.host_blocked", lambda host, resolve=True: host.startswith("127"))
    monkeypatch.setattr("sonoscribe.scout.tools.subprocess.run", lambda *a, **k: seen.append(a[0]) or None)
    text = open_page("nasa.gov")
    assert "Queued" in text
    assert "https://nasa.gov" in text
    assert seen == []
    assert take_queued_page() == "https://nasa.gov"
    search_text = open_page("", "avengers tickets")
    assert "google.com/search" in search_text
    assert seen == []
    with pytest.raises(ToolError):
        open_page("http://127.0.0.1/")


def test_fetch_wttr_uses_plain_place(monkeypatch) -> None:
    def fake_get(url, accept="text/plain, text/html", **_k):
        if "now" in url.lower():
            raise ToolError("Fetch failed (500).")
        if "Brooklyn" in url and "format=" in url:
            assert accept == "text/plain"
            return "Brooklyn: +72°F Sunny"
        raise ToolError("Fetch failed (500).")

    monkeypatch.setattr("sonoscribe.scout.tools.host_blocked", lambda host, resolve=True: False)
    monkeypatch.setattr("sonoscribe.scout.tools._http_get", fake_get)
    text = fetch_url("https://wttr.in/Brooklyn,%20New%20York%20now")
    assert "72" in text
    assert "Brooklyn" in text


def test_tool_payloads_stay_small() -> None:
    assert FETCH_LIMIT == 2500
    assert SEARCH_HITS == 3


def test_enabled_and_auto_tools() -> None:
    tasks = {"tools": ["search", "write_file"], "auto": ["write_file", "fetch"]}
    assert enabled_tools(tasks) == {"search", "write_file"}
    assert auto_tools(tasks) == {"write_file"}
    assert needs_confirm("search", tasks) is True
    assert needs_confirm("write_file", tasks) is False
    extra = [{"name": "mcp_m1_x", "mcp": True, "auto": False}]
    assert needs_confirm("mcp_m1_x", extra=extra) is True
    assert "weather" in enabled_tools()
    assert "capture_screen" not in enabled_tools()
    assert needs_confirm("weather") is False
    assert needs_confirm("capture_screen") is True


def test_capture_screen_is_opt_in_and_confirms() -> None:
    assert "capture_screen" not in enabled_tools({"tools": ["search", "fetch"]})
    assert enabled_tools({"tools": ["search", "capture_screen"]}) == {"search", "capture_screen"}
    assert needs_confirm("capture_screen", {"tools": ["capture_screen"]}) is True
    assert needs_confirm("capture_screen", {"tools": ["capture_screen"], "auto": ["capture_screen"]}) is False
    preview = confirm_preview("capture_screen", {})
    assert preview["title"] == "capture screen"


def test_capture_screen_queues_image(monkeypatch) -> None:
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def fake_run(cmd, **_kwargs):
        args = [str(item) for item in cmd]
        if args and args[0].endswith("screencapture"):
            Path(args[-1]).write_bytes(png)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if args and args[0].endswith("sips") and "--out" in args:
            Path(args[args.index("--out") + 1]).write_bytes(b"jpeg-bytes")
            return subprocess.CompletedProcess(cmd, 0, "pixelWidth: 1280\npixelHeight: 800\n", "")
        if args and args[0].endswith("sips"):
            return subprocess.CompletedProcess(cmd, 0, "pixelWidth: 1280\npixelHeight: 800\n", "")
        return subprocess.CompletedProcess(cmd, 1, "", "no")

    monkeypatch.setattr("sonoscribe.scout.tools.subprocess.run", fake_run)
    text = capture_screen()
    assert "Captured the current screen" in text
    assert "1280" in text
    shot = take_capture()
    assert shot is not None
    assert shot["mime"] == "image/jpeg"
    assert shot["data"]


def test_capture_screen_explains_permission(monkeypatch) -> None:
    monkeypatch.setattr(
        "sonoscribe.scout.tools.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", "denied"),
    )
    with pytest.raises(ToolError, match="Screen Recording"):
        capture_screen()


def test_library_tool_vocanote_is_auto_and_classifies() -> None:
    assert needs_confirm("library", args={"action": "list", "kind": "command"}) is False
    assert needs_confirm("library", args={"action": "upsert", "kind": "vocanote"}) is False
    assert needs_confirm("library", args={"action": "upsert", "kind": "command"}) is True
    assert needs_confirm("library", args={"action": "delete", "kind": "routine"}) is True
    text = run_tool(
        "library",
        {"action": "upsert", "kind": "vocanote", "item": {"title": "pay bills at 8 o'clock"}},
    )
    assert "pay bills at 8" in text
    listed = run_tool("library", {"action": "list", "kind": "note", "query": "bills"})
    assert "pay bills" in listed
