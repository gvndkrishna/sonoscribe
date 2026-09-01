import json
from urllib.request import Request, urlopen

from sonoscribe.catalog import empty_library
from sonoscribe.dashboard.server import DashboardServer, static_dir
from sonoscribe.stats import StatsStore


def test_static_assets_exist() -> None:
    root = static_dir()
    assert (root / "index.html").is_file()
    assert (root / "styles.css").is_file()
    assert (root / "app.js").is_file()


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
        with urlopen(server.url) as response:
            html = response.read().decode()
        assert "Sonoscribe" in html
    finally:
        server.stop()
