from urllib.parse import unquote

from sonoscribe.scout.live import live_kind, parse_bing_html, search_web, weather_lookup, wttr_place_candidates
from sonoscribe.scout.tools import ToolError, peek_queued_page, take_queued_page, weather


def test_live_kind() -> None:
    assert live_kind("weather in chicago") == "weather"
    assert live_kind("usd to inr") == "currency"
    assert live_kind("apple stock") == "stock"
    assert live_kind("time in tokyo") == "time"
    assert live_kind("breaking news") == "news"
    assert live_kind("iphone price") == "price"
    assert live_kind("largest continent") == ""


def test_wttr_place_candidates_drop_sentence_junk() -> None:
    dirty = wttr_place_candidates("weather in Brooklyn, New York now")
    assert dirty[0] == "Brooklyn, New York"
    assert "Brooklyn" in dirty
    spoken = wttr_place_candidates("weather in Brooklyn New York now")
    assert "Brooklyn" in spoken
    assert wttr_place_candidates("Paris,France")[0] in {"Paris,France", "Paris, France"}


def test_search_weather_uses_wttr(monkeypatch) -> None:
    def fake_get(url, accept="text/plain, text/html", **_k):
        if "wttr.in" in url:
            return "Chicago: +52°F Light rain"
        return "<html>anomaly.js?sv=html&cc=botnet</html>"

    monkeypatch.setattr("sonoscribe.scout.tools._http_get", fake_get)
    text = search_web("weather in chicago")
    assert text.startswith("live weather:")
    assert "52" in text
    assert "wttr.in" in text
    assert "accuweather.com" in text
    assert peek_queued_page() == ""


def test_weather_retries_brooklyn_after_dirty_wttr(monkeypatch) -> None:
    def fake_get(url, accept="text/plain, text/html", **_k):
        if "wttr.in" not in url:
            return "<html></html>"
        decoded = unquote(url)
        if "now" in decoded.lower():
            raise ToolError("Fetch failed (500).")
        if "Brooklyn" in decoded:
            return "Brooklyn: +72°F Sunny"
        return "Unknown location"

    monkeypatch.setattr("sonoscribe.scout.tools._http_get", fake_get)
    text = search_web("weather in Brooklyn, New York now")
    assert text.startswith("live weather:")
    assert "Brooklyn" in text
    assert "72" in text
    assert weather("Brooklyn").startswith("live weather:")
    assert "72" in weather_lookup("Brooklyn, New York now")


def test_search_currency_uses_frankfurter(monkeypatch) -> None:
    def fake_get(url, accept="text/plain, text/html", **_k):
        if "frankfurter.app" in url:
            return '{"amount":1.0,"base":"USD","date":"2026-04-08","rates":{"INR":83.2}}'
        return "<html></html>"

    monkeypatch.setattr("sonoscribe.scout.tools._http_get", fake_get)
    text = search_web("usd to inr")
    assert "1 USD = 83.2 INR" in text
    assert "frankfurter" in text


def test_search_live_miss_queues_web_page(monkeypatch) -> None:
    monkeypatch.setattr("sonoscribe.scout.tools._http_get", lambda *a, **k: "<html></html>")
    text = search_web("weather in zzz-unknown")
    assert "No live hits" in text
    assert "accuweather.com" in text
    assert "google.com/search" in text
    assert "Do not invent" in text
    assert "accuweather.com" in take_queued_page()


def test_search_falls_back_to_bing(monkeypatch) -> None:
    def fake_get(url, accept="text/plain, text/html", **_k):
        if "bing.com" in url:
            return """
            <li class="b_algo"><h2><a href="https://weather.gov/chicago">Chicago weather</a></h2>
            <p>52 and rain</p>
            """
        return "<html>anomaly.js?sv=html&cc=botnet</html>"

    monkeypatch.setattr("sonoscribe.scout.tools._http_get", fake_get)
    text = search_web("largest continent")
    assert "Chicago weather" in text
    assert "weather.gov/chicago" in text


def test_parse_bing_html() -> None:
    hits = parse_bing_html(
        """
        <li class="b_algo"><h2><a href="https://example.com/a">Alpha</a></h2><p>one</p>
        <li class="b_algo"><h2><a href="https://example.com/b">Beta</a></h2><p>two</p>
        """
    )
    assert hits[0]["title"] == "Alpha"
    assert hits[0]["url"] == "https://example.com/a"
    assert "one" in hits[0]["snippet"]
