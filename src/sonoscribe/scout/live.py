"""Live facts for time-sensitive scout asks. Search engines are a fallback."""

from __future__ import annotations

import json
import re
from urllib.parse import quote_plus

from sonoscribe.scout import tools as _tools

ToolError = _tools.ToolError
SEARCH_HITS = _tools.SEARCH_HITS


def _http_get(*args, **kwargs):
    return _tools._http_get(*args, **kwargs)


def html_to_text(raw: str) -> str:
    return _tools.html_to_text(raw)


def parse_search_html(raw: str) -> list[dict[str, str]]:
    return _tools.parse_search_html(raw)


def public_http_url(url: str) -> str:
    return _tools.public_http_url(url)


def _video_search_query(query: str) -> str:
    return _tools._video_search_query(query)


def _search_blocked(raw: str) -> bool:
    return _tools._search_blocked(raw)


def _wikipedia_hits(query: str) -> list[dict[str, str]]:
    return _tools._wikipedia_hits(query)

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)

_WEATHER = re.compile(
    r"\b(weather|forecast|temperature|\btemp\b|rain|snow|humidity|windy|accuweather)\b",
    re.IGNORECASE,
)
_FX = re.compile(
    r"\b(currency|exchange rate|forex|fx|usd|eur|gbp|inr|jpy|cad|aud|"
    r"rupee|rupees|dollar|dollars|euro|euros|yen|yuan|convert)\b",
    re.IGNORECASE,
)
_STOCK = re.compile(
    r"\b(stock|stocks|share price|ticker|nasdaq|dow(?:jones)?|s&p|nifty|sensex)\b",
    re.IGNORECASE,
)
_TIME = re.compile(
    r"\b(what(?:'s| is)|whats)?\s*(the )?(current )?time\b|\btime (?:in|now|zone)\b|\btimezone\b",
    re.IGNORECASE,
)
_NEWS = re.compile(r"\b(news|headline|headlines|breaking)\b", re.IGNORECASE)
_PRICE = re.compile(r"\b(price|prices|cost|how much|on sale|sale price)\b", re.IGNORECASE)
_WEATHER_STRIP = re.compile(
    r"\b(what(?:'s| is)|whats|how(?:'s| is)|current|today|tonight|right now|please|"
    r"weather|forecast|temperature|\btemp\b|rain|snow|humidity|wind|accuweather|"
    r"like|looking|in|for|at|the)\b",
    re.IGNORECASE,
)
_WTTR_JUNK = re.compile(
    r"\b(now|today|tonight|tomorrow|currently|current|please|this|"
    r"afternoon|morning|evening|night|weekend|week|days?|next|"
    r"right|just|there|here|conditions?)\b",
    re.IGNORECASE,
)
_WTTR_FORMAT = "%l:+%t+%c+%w+%h"
_ISO = (
    "USD",
    "EUR",
    "GBP",
    "INR",
    "JPY",
    "CAD",
    "AUD",
    "CHF",
    "CNY",
    "HKD",
    "SGD",
    "KRW",
    "BRL",
    "MXN",
    "NZD",
    "SEK",
    "NOK",
    "DKK",
    "ZAR",
    "AED",
)
_ISO_WORDS = {
    "dollar": "USD",
    "dollars": "USD",
    "euro": "EUR",
    "euros": "EUR",
    "rupee": "INR",
    "rupees": "INR",
    "pound": "GBP",
    "pounds": "GBP",
    "yen": "JPY",
    "yuan": "CNY",
}
_TICKER = re.compile(r"\$([A-Za-z]{1,5})\b")
_ENGINE_BLOCKED = re.compile(
    r"anomaly\.js|cc=botnet|unusual traffic|enable javascript|captcha",
    re.IGNORECASE,
)


def live_kind(query: str) -> str:
    text = str(query or "")
    if _WEATHER.search(text):
        return "weather"
    if _FX.search(text):
        return "currency"
    if _STOCK.search(text):
        return "stock"
    if _TIME.search(text):
        return "time"
    if _NEWS.search(text):
        return "news"
    if _PRICE.search(text):
        return "price"
    return ""


def google_search_url(query: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(query.strip())}"


def bing_search_url(query: str) -> str:
    return f"https://www.bing.com/search?q={quote_plus(query.strip())}"


def ddg_search_url(query: str) -> str:
    return f"https://duckduckgo.com/?q={quote_plus(query.strip())}"


def accuweather_url(place: str) -> str:
    q = quote_plus((place or "").strip() or "weather")
    return f"https://www.accuweather.com/en/search-locations?query={q}"


def google_news_url(query: str) -> str:
    return f"https://news.google.com/search?q={quote_plus(query.strip())}"


def search_web(query: str) -> str:
    q = str(query or "").strip()
    if not q:
        raise _tools.ToolError("Search needs a query.")
    kind = live_kind(q)
    live = _live_lookup(q, kind) if kind else None
    hits = _engine_hits(q, skip_wiki=bool(kind))
    if not hits and not kind:
        hits = _tools._wikipedia_hits(q)
    lines: list[str] = []
    if live:
        lines.append(f"live {live['kind']}: {live['fact']}")
        if live.get("source"):
            lines.append(f"source: {live['source']}")
        later = live.get("later") or ""
        if later:
            lines.append(f"later: {later}")
    if hits:
        body = "\n\n".join(f"{item['title']}\n{item['url']}\n{item['snippet']}" for item in hits)
        lines.append(_tools.wrap_untrusted(body))
    if lines:
        return "\n".join(lines)
    return _miss(q, kind)


def _miss(query: str, kind: str) -> str:
    pages = _fallback_pages(query, kind)
    if pages:
        _tools.queue_page(pages[0])
    listed = "\n".join(pages)
    return (
        "No live hits. Do not invent weather, prices, rates, times, or headlines. "
        "Put these pages in links. The browser opens when they click the notice.\n"
        f"{listed}"
    )


def _fallback_pages(query: str, kind: str) -> list[str]:
    pages: list[str] = []
    if kind == "weather":
        pages.append(accuweather_url((wttr_place_candidates(query) or [query])[0]))
    if kind == "news":
        pages.append(google_news_url(query))
    pages.extend([google_search_url(query), bing_search_url(query), ddg_search_url(query)])
    seen: set[str] = set()
    out: list[str] = []
    for url in pages:
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _live_lookup(query: str, kind: str) -> dict[str, str] | None:
    if kind == "weather":
        return _weather(query)
    if kind == "currency":
        return _currency(query)
    if kind == "stock":
        return _stock(query)
    if kind == "time":
        return _time(query)
    return None


def _weather_place(query: str) -> str:
    place = _WEATHER_STRIP.sub(" ", query)
    place = _WTTR_JUNK.sub(" ", place)
    place = re.sub(r"\s+", " ", place)
    place = re.sub(r"\s+,", ",", place)
    place = re.sub(r",\s+", ", ", place)
    return place.strip(" ?.,;:")


def wttr_place_candidates(query: str) -> list[str]:
    cleaned = _weather_place(query)
    out: list[str] = []

    def add(item: str) -> None:
        text = re.sub(r"\s+", " ", item).strip(" ?.,;:")
        if text and text.casefold() not in {item.casefold() for item in out}:
            out.append(text)

    if not cleaned:
        return out
    add(cleaned)
    add(cleaned.replace(", ", ","))
    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    if parts:
        add(parts[0])
        if len(parts) >= 2:
            add(parts[-1])
            add(f"{parts[0]},{parts[-1]}")
    words = [word for word in re.sub(r",", " ", cleaned).split() if word]
    if len(words) >= 2:
        add(words[0])
        add(" ".join(words[-2:]))
    return out


def wttr_url(place: str = "", *, compact: bool = True) -> str:
    path = quote_plus(place.strip()) if place.strip() else ""
    base = f"https://wttr.in/{path}" if path else "https://wttr.in/"
    if compact:
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}format={_WTTR_FORMAT}"
    return base


def weather_lookup(place: str) -> str:
    live = _weather(place)
    if not live:
        raise ToolError(
            "wttr.in had no reading. Pass a place the way wttr supports: "
            "Brooklyn, Chicago, Hyderabad, Paris,France, or JFK."
        )
    lines = [f"live weather: {live['fact']}", f"source: {live['source']}"]
    if live.get("later"):
        lines.append(f"later: {live['later']}")
    return "\n".join(lines)


def _weather(query: str) -> dict[str, str] | None:
    candidates = wttr_place_candidates(query)
    if not candidates:
        candidates = [""]
    for place in candidates:
        fact = _wttr_line(place)
        if fact:
            later = accuweather_url(place or fact.split(":", 1)[0])
            return {"kind": "weather", "fact": fact, "source": "wttr.in", "later": later}
    return None


def _wttr_line(place: str) -> str:
    try:
        raw = _http_get(wttr_url(place), accept="text/plain")
    except ToolError:
        return ""
    fact = html_to_text(raw).strip()
    if not fact or "unknown location" in fact.lower() or len(fact) > 160:
        return ""
    return fact


def _fx_codes(query: str) -> tuple[str, str] | None:
    found: list[str] = []
    for word in re.findall(r"[A-Za-z]+", query):
        upper = word.upper()
        if upper in _ISO and upper not in found:
            found.append(upper)
        else:
            mapped = _ISO_WORDS.get(word.lower())
            if mapped and mapped not in found:
                found.append(mapped)
        if len(found) == 2:
            return found[0], found[1]
    return None


def _currency(query: str) -> dict[str, str] | None:
    pair = _fx_codes(query)
    if not pair:
        return None
    src, dst = pair
    if src == dst:
        return None
    url = f"https://api.frankfurter.app/latest?from={src}&to={dst}"
    try:
        data = json.loads(_http_get(url, accept="application/json"))
    except (ToolError, json.JSONDecodeError, TypeError, ValueError):
        return None
    rates = data.get("rates") if isinstance(data, dict) else None
    if not isinstance(rates, dict) or dst not in rates:
        return None
    rate = rates.get(dst)
    date = str(data.get("date") or "").strip()
    fact = f"1 {src} = {rate} {dst}"
    if date:
        fact = f"{fact} ({date})"
    later = google_search_url(f"{src} to {dst}")
    return {"kind": "currency", "fact": fact, "source": "frankfurter", "later": later}


def _stock_symbol(query: str) -> str:
    tagged = _TICKER.search(query)
    if tagged:
        return tagged.group(1).upper()
    try:
        data = json.loads(
            _http_get(
                f"https://query1.finance.yahoo.com/v1/finance/search?q={quote_plus(query)}",
                accept="application/json",
            )
        )
    except (ToolError, json.JSONDecodeError, TypeError, ValueError):
        return ""
    quotes = data.get("quotes") if isinstance(data, dict) else None
    if not isinstance(quotes, list):
        return ""
    for item in quotes:
        if not isinstance(item, dict):
            continue
        if str(item.get("quoteType") or "") not in {"", "EQUITY", "ETF", "INDEX"}:
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if symbol:
            return symbol
    return ""


def _stock(query: str) -> dict[str, str] | None:
    symbol = _stock_symbol(query)
    if not symbol:
        return None
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote_plus(symbol)}?interval=1d&range=1d"
    try:
        data = json.loads(_http_get(url, accept="application/json"))
    except (ToolError, json.JSONDecodeError, TypeError, ValueError):
        return None
    chart = data.get("chart") if isinstance(data, dict) else None
    rows = chart.get("result") if isinstance(chart, dict) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None
    meta = rows[0].get("meta") if isinstance(rows[0].get("meta"), dict) else {}
    price = meta.get("regularMarketPrice")
    currency = str(meta.get("currency") or "").strip()
    if price in (None, ""):
        return None
    fact = f"{symbol} {price}"
    if currency:
        fact = f"{fact} {currency}"
    later = f"https://finance.yahoo.com/quote/{quote_plus(symbol)}"
    return {"kind": "stock", "fact": fact, "source": "yahoo finance", "later": later}


def _time(query: str) -> dict[str, str] | None:
    place = re.sub(
        r"\b(what(?:'s| is)|whats|current|please|time|now|in|for|at|the|timezone)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    place = re.sub(r"\s+", " ", place).strip(" ?.,")
    if place:
        url = f"https://wttr.in/{quote_plus(place)}?format=%l:+%T+%Z"
        try:
            raw = _http_get(url, accept="text/plain")
        except ToolError:
            raw = ""
        fact = html_to_text(raw).strip()
        if fact and "unknown location" not in fact.lower() and len(fact) < 120:
            return {"kind": "time", "fact": fact, "source": "wttr.in", "later": google_search_url(query)}
    try:
        data = json.loads(_http_get("https://worldtimeapi.org/api/ip", accept="application/json"))
    except (ToolError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    stamp = str(data.get("datetime") or "").strip()
    zone = str(data.get("timezone") or "").strip()
    if not stamp:
        return None
    fact = stamp[:19].replace("T", " ")
    if zone:
        fact = f"{fact} {zone}"
    return {"kind": "time", "fact": fact, "source": "worldtimeapi", "later": google_search_url(query)}


def _engine_hits(query: str, *, skip_wiki: bool) -> list[dict[str, str]]:
    q = _video_search_query(query)
    hits = _ddg_html_hits(q)
    if not hits:
        hits = _ddg_lite_hits(q)
    if not hits:
        hits = _bing_hits(q)
    if not hits:
        hits = _google_hits(q)
    if not hits and not skip_wiki:
        hits = _wikipedia_hits(query)
    return hits[:SEARCH_HITS]


def _ddg_html_hits(query: str) -> list[dict[str, str]]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        raw = _http_get(url, accept="text/html")
    except ToolError:
        return []
    if _search_blocked(raw) or _engine_blocked(raw):
        return []
    return parse_search_html(raw)


def _ddg_lite_hits(query: str) -> list[dict[str, str]]:
    url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
    try:
        raw = _http_get(url, accept="text/html")
    except ToolError:
        return []
    if _engine_blocked(raw):
        return []
    hits: list[dict[str, str]] = []
    for match in re.finditer(
        r'<a[^>]+rel="nofollow"[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
        raw,
        re.IGNORECASE | re.DOTALL,
    ):
        href = match.group(1)
        title = html_to_text(match.group(2))
        if not title or "duckduckgo.com" in href:
            continue
        if not public_http_url(href):
            continue
        hits.append({"title": title[:160], "url": href, "snippet": ""})
        if len(hits) >= SEARCH_HITS:
            break
    return hits


def _bing_hits(query: str) -> list[dict[str, str]]:
    url = bing_search_url(query)
    try:
        raw = _http_get(url, accept="text/html", user_agent=_BROWSER_UA)
    except ToolError:
        return []
    if _engine_blocked(raw):
        return []
    return parse_bing_html(raw)


def _google_hits(query: str) -> list[dict[str, str]]:
    url = google_search_url(query)
    try:
        raw = _http_get(url, accept="text/html", user_agent=_BROWSER_UA)
    except ToolError:
        return []
    if _engine_blocked(raw):
        return []
    return parse_google_html(raw)


def parse_bing_html(raw: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for match in re.finditer(
        r'<li class="b_algo".*?<h2>\s*<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
        raw or "",
        re.IGNORECASE | re.DOTALL,
    ):
        url = match.group(1)
        title = html_to_text(match.group(2))
        if not title or not public_http_url(url):
            continue
        snippet = ""
        tail = (raw or "")[match.end() : match.end() + 600]
        snip = re.search(r"<p>(.*?)</p>", tail, re.IGNORECASE | re.DOTALL)
        if snip:
            snippet = html_to_text(snip.group(1))[:240]
        hits.append({"title": title[:160], "url": url, "snippet": snippet})
        if len(hits) >= SEARCH_HITS:
            break
    return hits


def parse_google_html(raw: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r'href="(https?://[^"]+)"', raw or "", re.IGNORECASE):
        url = match.group(1)
        host = url.split("/", 3)[2].lower() if "://" in url else ""
        if "google." in host or "gstatic.com" in host or "youtube.com/results" in url:
            continue
        if url in seen or not public_http_url(url):
            continue
        seen.add(url)
        title = host
        hits.append({"title": title[:160], "url": url, "snippet": ""})
        if len(hits) >= SEARCH_HITS:
            break
    return hits


def _engine_blocked(raw: str) -> bool:
    return bool(_ENGINE_BLOCKED.search(raw or ""))
