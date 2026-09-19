"""Scout tools. Search and fetch run on their own. Writes wait for confirm."""

from __future__ import annotations

import base64
import html
import ipaddress
import json
import re
import socket
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from sonoscribe.scripts import RUNTIMES, ScriptError, assert_user_level

FETCH_LIMIT = 2500
FETCH_TIMEOUT = 10
SEARCH_HITS = 3
_SCRIPT_TIMEOUT = 30
_HOME = Path.home()
_queued_lock = threading.Lock()
_queued_page = ""
_capture_lock = threading.Lock()
_captured: dict[str, str] | None = None
CAPTURE_MAX_EDGE = 1280
DEFAULT_TOOLS = frozenset({"search", "weather", "fetch", "open_page", "run_script", "write_file", "read_file"})

AUTO_TOOLS = frozenset({"search", "weather", "fetch", "open_page"})
CONFIRM_TOOLS = frozenset({"run_script", "write_file", "read_file", "capture_screen"})

TOOL_SPECS = (
    {
        "name": "search",
        "description": "Live web facts for currency, time, news, prices, stocks. For weather, use weather with a wttr place. Videos go to YouTube or the named official host.",
        "schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "weather",
        "description": "Live weather from wttr.in. Figure the location, then pass a wttr place: city (Brooklyn), city,country (Paris,France), or airport (JFK). No sentences, no 'now' or 'weather in'.",
        "schema": {
            "type": "object",
            "properties": {"place": {"type": "string"}},
            "required": ["place"],
        },
    },
    {
        "name": "fetch",
        "description": "Fetch a public page as plain text.",
        "schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "open_page",
        "description": "Queue a site to open when they click the menu-bar notice. Does not open the browser now. Videos: YouTube or the official host. Pass a URL, domain, or query.",
        "schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "query": {"type": "string"},
            },
        },
    },
    {
        "name": "run_script",
        "description": "User-level bash or AppleScript. Needs confirm.",
        "schema": {
            "type": "object",
            "properties": {
                "runtime": {"type": "string", "enum": list(RUNTIMES)},
                "body": {"type": "string"},
            },
            "required": ["runtime", "body"],
        },
    },
    {
        "name": "write_file",
        "description": "Write a text file under home. Needs confirm.",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file under home. Needs confirm.",
        "schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "capture_screen",
        "description": "Capture the current display. Opt-in. Needs confirm unless they skip it. Use when they ask what is on screen.",
        "schema": {
            "type": "object",
            "properties": {},
        },
    },
)


class ToolError(ValueError):
    pass


def _scout_settings() -> dict[str, Any]:
    from sonoscribe.settings import load_settings

    data = load_settings().get("scout") or {}
    return data if isinstance(data, dict) else {}


def enabled_tools(scout: dict[str, Any] | None = None) -> frozenset[str]:
    data = scout if isinstance(scout, dict) else _scout_settings()
    raw = data.get("tools")
    names = {spec["name"] for spec in TOOL_SPECS}
    if not isinstance(raw, list):
        return frozenset(name for name in names if name in DEFAULT_TOOLS)
    return frozenset(str(item) for item in raw if str(item) in names)


def auto_tools(tasks: dict[str, Any] | None = None) -> frozenset[str]:
    data = tasks if isinstance(tasks, dict) else _scout_settings()
    enabled = enabled_tools(data)
    raw = data.get("auto")
    if not isinstance(raw, list):
        return AUTO_TOOLS & enabled
    return frozenset(str(item) for item in raw if str(item) in enabled)


def active_tool_specs(
    tasks: dict[str, Any] | None = None,
    extra: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    allowed = enabled_tools(tasks)
    specs = [dict(spec) for spec in TOOL_SPECS if spec["name"] in allowed]
    for item in extra or []:
        if isinstance(item, dict) and item.get("name"):
            specs.append(item)
    return specs


def needs_confirm(
    name: str,
    tasks: dict[str, Any] | None = None,
    extra: list[dict[str, Any]] | None = None,
    args: dict[str, Any] | None = None,
) -> bool:
    text = str(name or "")
    if text == "library":
        from sonoscribe.scribe.library import library_write_needs_confirm

        return library_write_needs_confirm(args)
    for spec in extra or []:
        if spec.get("name") != text:
            continue
        if spec.get("mcp"):
            return not bool(spec.get("auto"))
        break
    return text not in auto_tools(tasks)


def known_tool(name: str, tasks: dict[str, Any] | None = None, extra: list[dict[str, Any]] | None = None) -> bool:
    text = str(name or "")
    if any(spec.get("name") == text for spec in extra or []):
        return True
    return text in enabled_tools(tasks)


def confirm_preview(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "run_script":
        runtime = str(args.get("runtime") or "bash")
        body = str(args.get("body") or "")
        return {
            "tool": name,
            "args": {"runtime": runtime, "body": body},
            "title": f"run {runtime}",
            "preview": body[:1200],
        }
    if name == "write_file":
        path = str(args.get("path") or "")
        content = str(args.get("content") or "")
        return {
            "tool": name,
            "args": {"path": path, "content": content},
            "title": "write file",
            "preview": f"{path}\n\n{content[:800]}",
        }
    path = str(args.get("path") or "")
    if name == "read_file":
        return {
            "tool": name,
            "args": {"path": path},
            "title": "read file",
            "preview": path,
        }
    if name == "open_page":
        target = str(args.get("url") or args.get("query") or "")
        return {
            "tool": name,
            "args": args,
            "title": "open in browser",
            "preview": target[:1200],
        }
    if name == "capture_screen":
        return {
            "tool": name,
            "args": {},
            "title": "capture screen",
            "preview": "Capture the current display.",
        }
    if name == "library":
        action = str(args.get("action") or "library")
        kind = str(args.get("kind") or "")
        return {
            "tool": name,
            "args": args,
            "title": f"{action} {kind}".strip(),
            "preview": json.dumps(args, ensure_ascii=False)[:1200],
        }
    preview = json.dumps(args, ensure_ascii=False)[:1200] if args else name
    return {
        "tool": name,
        "args": args,
        "title": str(name or "tool"),
        "preview": preview,
    }


def run_tool(name: str, args: dict[str, Any]) -> str:
    if name == "search":
        return search(str(args.get("query") or ""))
    if name == "weather":
        return weather(str(args.get("place") or args.get("query") or ""))
    if name == "fetch":
        return fetch_url(str(args.get("url") or ""))
    if name == "open_page":
        return open_page(str(args.get("url") or ""), str(args.get("query") or ""))
    if name == "run_script":
        return run_user_script(str(args.get("runtime") or ""), str(args.get("body") or ""))
    if name == "write_file":
        return write_home_file(str(args.get("path") or ""), str(args.get("content") or ""))
    if name == "read_file":
        return read_home_file(str(args.get("path") or ""))
    if name == "capture_screen":
        return capture_screen()
    if name == "library":
        from sonoscribe.scribe.library import run_library

        return run_library(args)
    raise ToolError("Unknown tool.")


def search(query: str) -> str:
    from sonoscribe.scout.live import search_web

    return search_web(query)


def weather(place: str) -> str:
    from sonoscribe.scout.live import weather_lookup

    text = str(place or "").strip()
    if not text:
        raise ToolError("Weather needs a wttr place, like Brooklyn or Paris,France.")
    return weather_lookup(text)


def queue_page(url: str) -> str:
    global _queued_page
    cleaned = public_http_url(url)
    if not cleaned and str(url or "").strip():
        try:
            cleaned = public_http_url(browser_target(str(url or ""), ""))
        except Exception:
            cleaned = ""
    with _queued_lock:
        if cleaned:
            _queued_page = cleaned
        return _queued_page if cleaned else ""


def take_queued_page() -> str:
    global _queued_page
    with _queued_lock:
        url = _queued_page
        _queued_page = ""
        return url


def peek_queued_page() -> str:
    with _queued_lock:
        return _queued_page


def queue_capture(mime: str, data: str, width: int = 0, height: int = 0) -> None:
    global _captured
    body = str(data or "").strip()
    kind = str(mime or "image/jpeg").strip() or "image/jpeg"
    if not body:
        return
    with _capture_lock:
        _captured = {
            "mime": kind,
            "data": body,
            "width": str(max(0, int(width or 0))),
            "height": str(max(0, int(height or 0))),
        }


def take_capture() -> dict[str, str] | None:
    global _captured
    with _capture_lock:
        shot = _captured
        _captured = None
        return shot


def capture_screen() -> str:
    with tempfile.TemporaryDirectory(prefix="sonoscribe-screen-") as tmp:
        png = Path(tmp) / "screen.png"
        jpg = Path(tmp) / "screen.jpg"
        try:
            result = subprocess.run(
                ["/usr/sbin/screencapture", "-x", "-m", "-t", "png", str(png)],
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError("Could not capture the screen.") from exc
        if result.returncode != 0 or not png.is_file() or png.stat().st_size == 0:
            raise ToolError(
                "Screen capture failed. Allow Screen Recording for Sonoscribe in System Settings."
            )
        _shrink_capture(png, jpg)
        target = jpg if jpg.is_file() and jpg.stat().st_size else png
        payload = target.read_bytes()
        if not payload:
            raise ToolError("Screen capture was empty.")
        mime = "image/jpeg" if target.suffix.lower() == ".jpg" else "image/png"
        width, height = _image_size(target)
        queue_capture(mime, base64.b64encode(payload).decode("ascii"), width, height)
        if width and height:
            return f"Captured the current screen ({width}×{height})."
        return "Captured the current screen."


def _shrink_capture(src: Path, dest: Path) -> None:
    try:
        subprocess.run(
            [
                "/usr/bin/sips",
                "-Z",
                str(CAPTURE_MAX_EDGE),
                "-s",
                "format",
                "jpeg",
                "-s",
                "formatOptions",
                "70",
                str(src),
                "--out",
                str(dest),
            ],
            check=False,
            capture_output=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def _image_size(path: Path) -> tuple[int, int]:
    try:
        result = subprocess.run(
            ["/usr/bin/sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=4,
        )
    except (OSError, subprocess.TimeoutExpired):
        return (0, 0)
    width = _sips_number(result.stdout, "pixelWidth")
    height = _sips_number(result.stdout, "pixelHeight")
    return (width, height)


def _sips_number(text: str, key: str) -> int:
    match = re.search(rf"{re.escape(key)}:\s*(\d+)", text or "")
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def public_http_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if host_blocked(parsed.hostname or "", resolve=False):
        return ""
    return parsed.geturl()[:500]


def _search_blocked(raw: str) -> bool:
    low = (raw or "").lower()
    return "anomaly.js" in low or "cc=botnet" in low


def _wikipedia_hits(query: str) -> list[dict[str, str]]:
    url = (
        "https://en.wikipedia.org/w/api.php?action=query&list=search"
        f"&utf8=1&format=json&srlimit={SEARCH_HITS}&srsearch={quote_plus(query)}"
    )
    try:
        data = json.loads(_http_get(url, accept="application/json"))
    except (ToolError, json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    hits: list[dict[str, str]] = []
    for item in ((data.get("query") or {}).get("search") or []):
        if not isinstance(item, dict):
            continue
        title = html_to_text(str(item.get("title") or ""))
        if not title:
            continue
        page = quote(title.replace(" ", "_"), safe="()'!*,-./:;@_")
        hits.append(
            {
                "title": title[:160],
                "url": f"https://en.wikipedia.org/wiki/{page}",
                "snippet": html_to_text(str(item.get("snippet") or ""))[:240],
            }
        )
        if len(hits) >= SEARCH_HITS:
            break
    return hits


_VIDEO_TERMS = re.compile(
    r"\b(youtube|youtu\.be|\byt\b|trailer|trailers|music video|videos?|clips?|"
    r"highlights?|episode|livestream|netflix|vimeo|twitch|dailymotion|"
    r"disney\+|disney plus|prime video|amazon prime|hulu|\bhbo\b|hbo max|"
    r"apple tv)\b",
    re.IGNORECASE,
)
_WATCH_VERB = re.compile(r"^\s*(please\s+)?watch\b", re.IGNORECASE)
_DEVICE_WATCH = re.compile(r"\b(apple|galaxy|samsung|pixel|fitbit)\s+watch\b", re.IGNORECASE)
_PLATFORM_TERMS = (
    (re.compile(r"\b(youtube|youtu\.be|\byt\b)\b", re.IGNORECASE), "youtube"),
    (re.compile(r"\bvimeo\b", re.IGNORECASE), "vimeo"),
    (re.compile(r"\bnetflix\b", re.IGNORECASE), "netflix"),
    (re.compile(r"\b(prime video|amazon prime)\b", re.IGNORECASE), "prime"),
    (re.compile(r"\b(disney\+|disney plus)\b", re.IGNORECASE), "disney"),
    (re.compile(r"\btwitch\b", re.IGNORECASE), "twitch"),
    (re.compile(r"\bdailymotion\b", re.IGNORECASE), "dailymotion"),
    (re.compile(r"\b(hbo max|\bhbo\b)\b", re.IGNORECASE), "max"),
    (re.compile(r"\bhulu\b", re.IGNORECASE), "hulu"),
    (re.compile(r"\bapple tv\b", re.IGNORECASE), "appletv"),
)
_PLATFORM_HOSTS = {
    "youtube": "youtube.com",
    "vimeo": "vimeo.com",
    "netflix": "netflix.com",
    "prime": "primevideo.com",
    "disney": "disneyplus.com",
    "twitch": "twitch.tv",
    "dailymotion": "dailymotion.com",
    "max": "max.com",
    "hulu": "hulu.com",
    "appletv": "tv.apple.com",
}
_PLATFORM_ALIASES = {
    "youtu.be": "youtube",
    "m.youtube.com": "youtube",
    "www.youtube.com": "youtube",
    "music.youtube.com": "youtube",
}
_STRIP_VIDEO = re.compile(
    r"\b(on )?(youtube|youtu\.be|\byt\b|netflix|vimeo|twitch|dailymotion|"
    r"disney\+|disney plus|prime video|amazon prime|hulu|hbo max|\bhbo\b|apple tv)\b|"
    r"\b(please|watch|play|open|find|search for|search)\b",
    re.IGNORECASE,
)


def video_intent(text: str) -> bool:
    body = str(text or "").strip()
    if not body:
        return False
    if _DEVICE_WATCH.search(body) and not _VIDEO_TERMS.search(body):
        return False
    if _VIDEO_TERMS.search(body):
        return True
    return bool(_WATCH_VERB.search(body))


def named_video_platform(text: str) -> str:
    body = str(text or "")
    for pattern, name in _PLATFORM_TERMS:
        if pattern.search(body):
            return name
    return ""


def video_query(text: str) -> str:
    cleaned = _STRIP_VIDEO.sub(" ", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or str(text or "").strip()


def host_video_platform(host: str) -> str:
    raw = str(host or "").strip().lower().rstrip(".")
    if raw.startswith("www."):
        raw = raw[4:]
    if raw in _PLATFORM_ALIASES:
        return _PLATFORM_ALIASES[raw]
    for name, domain in _PLATFORM_HOSTS.items():
        if raw == domain or raw.endswith("." + domain):
            return name
    return ""


def platform_search_url(platform: str, query: str) -> str:
    q = quote_plus(query.strip())
    if platform == "vimeo":
        return f"https://vimeo.com/search?q={q}"
    if platform == "netflix":
        return f"https://www.netflix.com/search?q={q}"
    if platform == "prime":
        return f"https://www.primevideo.com/search?phrase={q}"
    if platform == "disney":
        return f"https://www.disneyplus.com/search?q={q}"
    if platform == "twitch":
        return f"https://www.twitch.tv/search?term={q}"
    if platform == "dailymotion":
        return f"https://www.dailymotion.com/search/{q}"
    if platform == "max":
        return f"https://www.max.com/search?q={q}"
    if platform == "hulu":
        return f"https://www.hulu.com/search?q={q}"
    if platform == "appletv":
        return f"https://tv.apple.com/search?term={q}"
    return f"https://www.youtube.com/results?search_query={q}"


def _video_search_query(query: str) -> str:
    q = query.strip()
    if "site:" in q.lower() or "://" in q:
        return q
    named = named_video_platform(q)
    if named:
        return f"{q} site:{_PLATFORM_HOSTS[named]}"
    if video_intent(q):
        return f"{q} site:youtube.com"
    return q


def _google_search_url(query: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(query)}"


def _bare_site_home(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "/").rstrip("/")
    return not path and not parsed.query


def browser_target(url: str = "", query: str = "") -> str:
    target = str(url or "").strip()
    q = str(query or "").strip()
    combined = " ".join(part for part in (target, q) if part and "://" not in part)
    named = named_video_platform(combined)
    video = video_intent(combined)
    phrase = video_query(q or (target if target and "://" not in target and "." not in target else "")) or q
    if target and "://" in target:
        if q and _bare_site_home(target):
            host = urlparse(target).hostname or ""
            platform = host_video_platform(host) or named
            if platform:
                return platform_search_url(platform, phrase or q)
        return target
    if target and "." in target:
        if q and (host_video_platform(target) or named or video):
            platform = host_video_platform(target) or named or "youtube"
            return platform_search_url(platform, phrase or q)
        return "https://" + target.lstrip("/")
    text = q or target
    if not text:
        return ""
    if named or video:
        return platform_search_url(named or "youtube", phrase or text)
    return _google_search_url(text)


def fetch_url(url: str) -> str:
    cleaned = assert_public_http_url(url)
    host = (urlparse(cleaned).hostname or "").lower()
    if host == "wttr.in" or host.endswith(".wttr.in"):
        return _fetch_wttr(cleaned)
    raw = _http_get(cleaned)
    text = html_to_text(raw)[:FETCH_LIMIT]
    if not text:
        raise ToolError("Page had no text.")
    return f"untrusted web text:\n{text}"


def _fetch_wttr(url: str) -> str:
    from sonoscribe.scout.live import wttr_place_candidates, wttr_url

    parsed = urlparse(url)
    place = unquote((parsed.path or "/").strip("/"))
    targets: list[str] = []
    if "format=" in (parsed.query or ""):
        targets.append(url)
    for candidate in wttr_place_candidates(place) or [place]:
        compact = wttr_url(candidate)
        if compact not in targets:
            targets.append(compact)
    last = "Page had no text."
    for target in targets:
        try:
            raw = _http_get(target, accept="text/plain")
        except ToolError as exc:
            last = str(exc)
            continue
        text = html_to_text(raw).strip()[:FETCH_LIMIT]
        if text and "unknown location" not in text.lower() and len(text) <= 160:
            return f"untrusted web text:\n{text}"
    raise ToolError(last)


def open_page(url: str = "", query: str = "") -> str:
    target = browser_target(url, query)
    if not target:
        raise ToolError("Need a URL or a search.")
    cleaned = assert_public_http_url(target)
    queue_page(cleaned)
    return (
        f"Queued {cleaned}. Put it in links. The browser opens when they click the notice. "
        "Do not say you opened it."
    )


def open_queued_page(url: str) -> str:
    cleaned = assert_public_http_url(url)
    try:
        subprocess.run(["open", cleaned], check=False, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolError("Could not open the browser.") from exc
    return cleaned


def run_user_script(runtime: str, body: str) -> str:
    kind = runtime if runtime in RUNTIMES else ""
    if not kind:
        raise ToolError("Script runtime must be bash or applescript.")
    text = body.strip()
    if not text:
        raise ToolError("Script is empty.")
    try:
        assert_user_level(text)
    except ScriptError as exc:
        raise ToolError(str(exc)) from exc
    suffix = ".applescript" if kind == "applescript" else ".sh"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=suffix, delete=True) as handle:
        handle.write(text)
        handle.flush()
        cmd = ["/usr/bin/osascript", handle.name] if kind == "applescript" else ["/bin/bash", handle.name]
        try:
            result = subprocess.run(
                cmd,
                check=False,
                timeout=_SCRIPT_TIMEOUT,
                cwd=str(_HOME),
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError("Script timed out.") from exc
    out = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    if result.returncode != 0 and not out:
        raise ToolError(f"Script exited {result.returncode}.")
    return out or "ok"


def write_home_file(path: str, content: str) -> str:
    target = resolve_home_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"wrote {target}"


def read_home_file(path: str) -> str:
    target = resolve_home_path(path)
    if not target.is_file():
        raise ToolError("File was not found.")
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ToolError(f"Could not read file: {exc}") from exc
    return text[:FETCH_LIMIT]


def resolve_home_path(raw: str) -> Path:
    text = str(raw or "").strip()
    if not text:
        raise ToolError("Path is required.")
    try:
        path = Path(text).expanduser().resolve()
        home = _HOME.resolve()
    except OSError as exc:
        raise ToolError(f"Invalid path: {exc}") from exc
    if path != home and home not in path.parents:
        raise ToolError("Path must stay under your home folder.")
    return path


def assert_public_http_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ToolError("Only public http and https URLs are allowed.")
    host = parsed.hostname or ""
    if not host or host_blocked(host, resolve=True):
        raise ToolError("That host is not allowed.")
    return parsed.geturl()


def host_blocked(host: str, *, resolve: bool = True) -> bool:
    name = host.strip().rstrip(".").lower()
    if not name or name == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        ip = None
    if ip is not None:
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
    if not resolve:
        return False
    try:
        infos = socket.getaddrinfo(name, None)
    except socket.gaierror:
        return True
    for info in infos:
        raw = info[4][0]
        try:
            found = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if found.is_private or found.is_loopback or found.is_link_local or found.is_reserved or found.is_multicast:
            return True
    return False


def parse_search_html(raw: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for match in re.finditer(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        raw,
        re.IGNORECASE | re.DOTALL,
    ):
        url = _ddg_url(html.unescape(match.group(1)))
        title = html_to_text(match.group(2))
        if not url or not title:
            continue
        snippet = ""
        tail = raw[match.end() : match.end() + 800]
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)', tail, re.IGNORECASE | re.DOTALL)
        if snip:
            snippet = html_to_text(snip.group(1))[:240]
        hits.append({"title": title[:160], "url": url, "snippet": snippet})
        if len(hits) >= SEARCH_HITS:
            break
    return hits


def html_to_text(raw: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw or "")
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def wrap_untrusted(text: str) -> str:
    body = str(text or "")
    if body.startswith("untrusted web text:"):
        return body
    return f"untrusted web text:\n{body}"


def _ddg_url(href: str) -> str:
    parsed = urlparse(href)
    if "duckduckgo.com" in (parsed.netloc or "") and parsed.path.startswith("/l/"):
        uddg = (parse_qs(parsed.query).get("uddg") or [""])[0]
        href = unquote(uddg) if uddg else href
    parsed = urlparse(href)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if host_blocked(parsed.hostname or "", resolve=False):
        return ""
    return parsed.geturl()


def _http_get(url: str, accept: str = "text/plain, text/html", user_agent: str = "") -> str:
    request = Request(
        url,
        headers={
            "User-Agent": user_agent
            or "Sonoscribe/1.0 (+https://github.com/gvndkrishna/sonoscribe)",
            "Accept": accept,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT) as response:
            content_type = str(response.headers.get("Content-Type") or "")
            if content_type.startswith(("image/", "audio/", "video/", "application/octet-stream")):
                raise ToolError("Binary responses are skipped.")
            data = response.read(FETCH_LIMIT * 4)
    except HTTPError as exc:
        raise ToolError(f"Fetch failed ({exc.code}).") from exc
    except URLError as exc:
        raise ToolError("Could not reach that page.") from exc
    except TimeoutError as exc:
        raise ToolError("Fetch timed out.") from exc
    try:
        return data.decode("utf-8", errors="replace")
    except Exception as exc:
        raise ToolError("Could not read that page.") from exc
