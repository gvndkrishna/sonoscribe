"""Local vocanote parse: title stays as spoken, clock and to-do flags inferred."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

_LEAD = re.compile(r"^(?:please|pls|kindly)\s+", re.IGNORECASE)
_TODO_PHRASE = re.compile(
    r"^(?:don'?t\s+forget|do\s+not\s+forget|remember(?:\s+to)?|pick\s+up|to-?do)\b",
    re.IGNORECASE,
)
_FIRST = re.compile(r"^([a-z][a-z']*)", re.IGNORECASE)
_VERBS = frozenset(
    """
    accept add adjust answer apply arrange ask attach attend
    back bake book borrow bring brush build buy
    call cancel change charge check choose clean clear close collect confirm cook copy count create cut
    delete deliver discuss do download draft draw drink drive drop dry
    eat edit email empty end enter erase exercise explain export
    feed file fill find finish fix fold follow forget forward
    get give go grab
    hang help hide hold
    import install invite iron
    join
    keep
    leave lend list listen load lock look
    mail make mark measure meet message move mow
    open order organize
    pack paint pay phone pick place plan plant play plug post pour practice prepare print pull push put
    read refill remember remind remove rename rent reply report reset rest restock return review rinse run
    save say schedule scrape search sell send set sew share shave ship show shut sign skip sort start stay
    stop store stretch study submit sweep switch
    take talk tap tell test text throw tidy tie tighten track transfer try turn type
    unplug update upload use
    vacuum visit
    wait wake walk wash watch water wear wipe write
    """.split()
)
_ING_NOUN = frozenset({"meeting", "morning", "evening", "wedding", "meaning", "feeling"})
_HOUR_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_HOUR = r"(?:[01]?\d|2[0-3]|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_CLOCK_TAIL = r"(?:\s*[:.]\s*(\d{2}))?\s*(?:o'?clock|oclock|o\s+clock)?(?:\s*(a\.?m\.?|p\.?m\.?))?"
_AT_CLOCK = re.compile(rf"\b(?:at|by)\s+({_HOUR}){_CLOCK_TAIL}", re.IGNORECASE)
_MERIDIEM = re.compile(rf"\b({_HOUR})(?:\s*[:.]\s*(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b", re.IGNORECASE)
_OCLOCK = re.compile(rf"\b({_HOUR})(?:\s*[:.]\s*(\d{2}))?\s*(?:o'?clock|oclock|o\s+clock)\b(?:\s*(a\.?m\.?|p\.?m\.?))?", re.IGNORECASE)
_IN_REL = re.compile(
    r"\bin\s+(?:an?\s+)?(\d+)?\s*(minutes?|mins?|hours?|hrs?)\b",
    re.IGNORECASE,
)
_NOON = re.compile(r"\b(?:at\s+)?noon\b", re.IGNORECASE)
_MIDNIGHT = re.compile(r"\b(?:at\s+)?midnight\b", re.IGNORECASE)
_TOMORROW = re.compile(r"\btomorrow\b", re.IGNORECASE)
_TONIGHT = re.compile(r"\b(?:tonight|this\s+evening|this\s+eve)\b", re.IGNORECASE)
_AFTERNOON = re.compile(r"\bthis\s+afternoon\b", re.IGNORECASE)
_THIS_MORNING = re.compile(r"\bthis\s+morning\b", re.IGNORECASE)
_TOMORROW_MORNING = re.compile(r"\btomorrow\s+morning\b", re.IGNORECASE)
_TOMORROW_NIGHT = re.compile(r"\btomorrow\s+(?:night|evening)\b", re.IGNORECASE)
_REMIND = re.compile(
    r"\b(?:remind(?:ing)?(?:\s+me)?|set\s+a\s+reminder|don'?t\s+forget|do\s+not\s+forget)\b",
    re.IGNORECASE,
)
_SAVE_ASK = re.compile(
    r"(?i)\b(?:add(?:ed)?|save|put|create|set|make)\b.+\b(?:reminders?|scribe|vocanotes?|to-?dos?|notes?|list)\b"
    r"|\bremind(?:ing)?\s+me\b"
    r"|\bset\s+a\s+reminder\b"
)
_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_NAMED_DATE = re.compile(
    rf"""
    \b(?:
        (?P<m1>{_MONTH_ALT})\.?\s+(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?(?:,\s*|\s+)(?P<y1>\d{{4}})
        |
        (?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<m2>{_MONTH_ALT})\.?,?\s+(?P<y2>\d{{4}})
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}
_WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_REPEAT_KINDS = frozenset({"daily", "weekly", "weekdays", "weekends", *_WEEKDAY_NAMES})
_WEEKDAY_ALT = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))
_REPEAT = re.compile(
    rf"""
    \b(?:
        (?P<daily>every\s+day|everyday|each\s+day|daily|every\s+morning|every\s+evening|every\s+night)
        |
        (?P<weekdays>every\s+weekdays?|weekdays)
        |
        (?P<weekends>every\s+weekends?|weekends)
        |
        (?P<weekly>every\s+week|weekly)
        |
        every\s+(?P<every_day>{_WEEKDAY_ALT})s?
        |
        (?P<days>{_WEEKDAY_ALT})s
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
_NAMED_DAY = re.compile(
    rf"""
    \b(?:
        (?P<next_week>next\s+week)
        |
        (?P<next_weekend>next\s+weekend)
        |
        (?P<weekend>this\s+weekend|(?<!next\s)weekend)
        |
        (?P<next>next\s+)(?P<next_day>{_WEEKDAY_ALT})
        |
        (?:this\s+|on\s+)?(?P<day>{_WEEKDAY_ALT})
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def local_now() -> datetime:
    return datetime.now().astimezone()


def next_clock(
    hour: int,
    minute: int = 0,
    *,
    now: datetime | None = None,
    meridiem: str | None = None,
) -> datetime:
    stamp = now or local_now()
    if stamp.tzinfo is None:
        stamp = stamp.astimezone()
    hour = int(hour)
    minute = max(0, min(59, int(minute)))
    mer = (meridiem or "").strip().lower().replace(".", "")
    if mer.startswith("a"):
        return _next_at(stamp, 0 if hour == 12 else hour if hour <= 12 else hour, minute)
    if mer.startswith("p"):
        if hour > 12:
            return _next_at(stamp, hour, minute)
        return _next_at(stamp, 12 if hour == 12 else hour + 12, minute)
    if hour > 12 or hour == 0:
        return _next_at(stamp, hour % 24, minute)
    am = 0 if hour == 12 else hour
    pm = 12 if hour == 12 else hour + 12
    found: list[datetime] = []
    for value in (am, pm):
        candidate = stamp.replace(hour=value, minute=minute, second=0, microsecond=0)
        if candidate > stamp:
            found.append(candidate)
    found.append((stamp + timedelta(days=1)).replace(hour=am, minute=minute, second=0, microsecond=0))
    return min(found)


def wants_scribe_save(text: str) -> bool:
    raw = " ".join(str(text or "").split())
    return bool(raw) and bool(_SAVE_ASK.search(raw))


def parse_scribe(text: str, *, now: datetime | None = None) -> dict[str, Any]:
    title = " ".join(str(text or "").split()).strip()
    stamp = now or local_now()
    if stamp.tzinfo is None:
        stamp = stamp.astimezone()
    repeat = repeat_from_text(title)
    due = _due_from_text(title, stamp, repeat)
    if due is None and (repeat or _REMIND.search(title)):
        due = (
            next_repeat_due(repeat, stamp, hour=_repeat_hour(title, repeat))
            if repeat
            else next_clock(8, now=stamp)
        )
    return {
        "title": title or "note",
        "body": "",
        "is_note": True,
        "is_todo": _starts_with_verb(title),
        "is_reminder": due is not None,
        "due_at": due.isoformat(timespec="seconds") if due else "",
        "repeat": repeat,
    }


def normalize_repeat(raw: Any) -> str:
    text = str(raw or "").strip().lower().replace("_", " ")
    if text in {"every day", "everyday", "each day", "nightly"}:
        return "daily"
    if text in {"every weekday", "every weekdays"}:
        return "weekdays"
    if text in {"every weekend", "every weekends"}:
        return "weekends"
    if text in {"every week"}:
        return "weekly"
    if text.startswith("every "):
        text = text[6:].rstrip("s")
    if text.endswith("s") and text[:-1] in _WEEKDAYS:
        text = text[:-1]
    if text in _WEEKDAYS:
        return _WEEKDAY_NAMES[_WEEKDAYS[text]]
    return text if text in _REPEAT_KINDS else ""


def repeat_from_text(text: str) -> str:
    hit = _REPEAT.search(str(text or ""))
    if hit is None:
        return ""
    if hit.group("daily"):
        return "daily"
    if hit.group("weekdays"):
        return "weekdays"
    if hit.group("weekends"):
        return "weekends"
    if hit.group("weekly"):
        return "weekly"
    named = hit.group("every_day") or hit.group("days")
    return normalize_repeat(named)


def next_repeat_due(
    repeat: str,
    now: datetime,
    *,
    hour: int = 8,
    minute: int = 0,
    strict: bool = False,
) -> datetime:
    kind = normalize_repeat(repeat)
    stamp = now if now.tzinfo else now.astimezone()
    hour = max(0, min(23, int(hour)))
    minute = max(0, min(59, int(minute)))
    if kind == "daily":
        return _next_daily(stamp, hour, minute, strict)
    if kind == "weekly":
        return _next_dow(stamp, stamp.weekday(), hour, minute, include_today=not strict)
    if kind == "weekdays":
        return _next_in_days(stamp, hour, minute, {0, 1, 2, 3, 4}, strict)
    if kind == "weekends":
        return _next_in_days(stamp, hour, minute, {5, 6}, strict)
    if kind in _WEEKDAYS:
        return _next_dow(stamp, _WEEKDAYS[kind], hour, minute, include_today=not strict)
    return _next_daily(stamp, hour, minute, strict)


def _starts_with_verb(text: str) -> bool:
    title = _LEAD.sub("", " ".join(str(text or "").split()).strip())
    if not title:
        return False
    if _TODO_PHRASE.match(title):
        return True
    hit = _FIRST.match(title)
    if hit is None:
        return False
    return _is_verb(hit.group(1))


def _is_verb(word: str) -> bool:
    raw = str(word or "").strip().lower()
    if not raw or raw in _ING_NOUN:
        return False
    if raw in _VERBS:
        return True
    stems = {raw}
    if raw.endswith("ies") and len(raw) > 4:
        stems.add(raw[:-3] + "y")
    if raw.endswith("es") and len(raw) > 3:
        stems.add(raw[:-2])
    if raw.endswith("s") and not raw.endswith("ss") and len(raw) > 2:
        stems.add(raw[:-1])
    if raw.endswith("ied") and len(raw) > 4:
        stems.add(raw[:-3] + "y")
    if raw.endswith("ed") and len(raw) > 3:
        stems.add(raw[:-2])
        stems.add(raw[:-1])
        if len(raw) > 4 and raw[-3] == raw[-4]:
            stems.add(raw[:-3])
    if raw.endswith("ing") and len(raw) > 4:
        stem = raw[:-3]
        stems.add(stem)
        stems.add(stem + "e")
        if len(stem) > 1 and stem[-1] == stem[-2]:
            stems.add(stem[:-1])
    return any(item in _VERBS for item in stems)


def coerce_due(raw: Any, *, now: datetime | None = None) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}T", text):
        parsed = parse_stamp(text)
        return parsed.isoformat(timespec="seconds") if parsed else ""
    found = _due_from_text(text, now or local_now(), repeat_from_text(text))
    if found is not None:
        return found.isoformat(timespec="seconds")
    parsed = parse_stamp(text)
    return parsed.isoformat(timespec="seconds") if parsed else ""


def parse_stamp(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_now().tzinfo)
    return parsed


def _due_from_text(text: str, now: datetime, repeat: str = "") -> datetime | None:
    day = _calendar_date(text, now) or _named_day(text, now, repeat)
    relative = _IN_REL.search(text)
    if relative:
        count = int(relative.group(1) or 1)
        unit = relative.group(2).lower()
        if unit.startswith("hour") or unit.startswith("hr"):
            return now + timedelta(hours=count)
        return now + timedelta(minutes=count)
    if _NOON.search(text):
        if day is not None:
            return _on_calendar(day, 12, 0, "pm")
        due = _next_at(now, 12, 0)
        return _nudge_tomorrow(text, now, due, 12, 0, "pm")
    if _MIDNIGHT.search(text):
        if day is not None:
            return _on_calendar(day, 0, 0, None)
        return _next_at(now, 0, 0)
    hit = _AT_CLOCK.search(text) or _MERIDIEM.search(text) or _OCLOCK.search(text)
    if hit is None:
        if day is not None:
            return _on_calendar(day, 8, 0, "am")
        period = _due_from_period(text, now)
        if period is not None:
            return period
        if repeat:
            return next_repeat_due(repeat, now, hour=_repeat_hour(text, repeat))
        return None
    hour = _parse_hour(hit.group(1))
    minute = int(hit.group(2) or 0)
    mer = _meridiem(hit) or _period_meridiem(text)
    if hour is None:
        if day is not None:
            return _on_calendar(day, 8, 0, "am")
        period = _due_from_period(text, now)
        if period is not None:
            return period
        if repeat:
            return next_repeat_due(repeat, now, hour=_repeat_hour(text, repeat))
        return None
    if day is not None:
        return _on_calendar(day, hour, minute, mer)
    if _TOMORROW.search(text) and mer is None and 1 <= hour <= 12:
        am = 0 if hour == 12 else hour
        return (now + timedelta(days=1)).replace(hour=am, minute=minute, second=0, microsecond=0)
    due = next_clock(hour, minute, now=now, meridiem=mer)
    return _nudge_tomorrow(text, now, due, hour, minute, mer)


def _named_day(text: str, now: datetime, repeat: str = "") -> datetime | None:
    kind = normalize_repeat(repeat)
    if kind in _WEEKDAYS:
        return _next_dow(now, _WEEKDAYS[kind], 8, 0, include_today=True)
    if kind in {"daily", "weekly", "weekdays", "weekends"}:
        return None
    hit = _NAMED_DAY.search(str(text or ""))
    if hit is None:
        return None
    if hit.group("next_week"):
        start = now.replace(hour=8, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
        return start + timedelta(days=7)
    if hit.group("next_weekend"):
        start = now.replace(hour=8, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
        return start + timedelta(days=12)
    if hit.group("weekend"):
        return _this_weekend(now)
    if hit.group("next_day"):
        return _next_dow(now, _WEEKDAYS[hit.group("next_day").lower()], 8, 0, include_today=False)
    if hit.group("day"):
        return _next_dow(now, _WEEKDAYS[hit.group("day").lower()], 8, 0, include_today=True)
    return None


def _repeat_hour(text: str, repeat: str) -> int:
    if normalize_repeat(repeat) != "daily":
        return 8
    raw = str(text or "")
    if re.search(r"(?i)\bevery\s+(evening|night)\b", raw):
        return 20
    if re.search(r"(?i)\bevery\s+afternoon\b", raw):
        return 15
    return 8


def _this_weekend(now: datetime) -> datetime:
    eight = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if now.weekday() == 5:
        if eight > now:
            return eight
        sunday = eight + timedelta(days=1)
        return sunday if sunday > now else eight + timedelta(days=7)
    if now.weekday() == 6:
        return eight if eight > now else eight + timedelta(days=6)
    return _next_dow(now, 5, 8, 0, include_today=True)


def _next_dow(now: datetime, dow: int, hour: int, minute: int, *, include_today: bool) -> datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta = (int(dow) - now.weekday()) % 7
    if delta:
        return candidate + timedelta(days=delta)
    if include_today and candidate > now:
        return candidate
    return candidate + timedelta(days=7)


def _next_daily(now: datetime, hour: int, minute: int, strict: bool) -> datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if not strict and candidate > now:
        return candidate
    return candidate + timedelta(days=1)


def _next_in_days(now: datetime, hour: int, minute: int, days: set[int], strict: bool) -> datetime:
    start = 1 if strict else 0
    for add in range(start, 8):
        day = now + timedelta(days=add)
        if day.weekday() not in days:
            continue
        candidate = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate
    return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)


def _calendar_date(text: str, now: datetime) -> datetime | None:
    named = _NAMED_DATE.search(text)
    if named:
        if named.group("m1"):
            month = _MONTHS[named.group("m1").lower()]
            day = int(named.group("d1"))
            year = int(named.group("y1"))
        else:
            month = _MONTHS[named.group("m2").lower()]
            day = int(named.group("d2"))
            year = int(named.group("y2"))
        return _safe_date(now, year, month, day)
    iso = _ISO_DATE.search(text)
    if iso:
        return _safe_date(now, int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    return None


def _safe_date(now: datetime, year: int, month: int, day: int) -> datetime | None:
    try:
        return now.replace(year=year, month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        return None


def _on_calendar(day: datetime, hour: int, minute: int, mer: str | None) -> datetime:
    hour = int(hour)
    minute = max(0, min(59, int(minute)))
    mark = (mer or "").strip().lower().replace(".", "")
    if mark.startswith("a"):
        hour = 0 if hour == 12 else hour if hour <= 12 else hour % 24
    elif mark.startswith("p"):
        if hour < 12:
            hour += 12
        elif hour > 12:
            hour = hour % 24
    else:
        hour = max(0, min(23, hour))
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _nudge_tomorrow(
    text: str,
    now: datetime,
    due: datetime,
    hour: int,
    minute: int,
    mer: str | None,
) -> datetime:
    if not _TOMORROW.search(text) or due.date() != now.date():
        return due
    if mer:
        return due + timedelta(days=1)
    am = 0 if hour == 12 else hour if hour <= 12 else hour
    return (now + timedelta(days=1)).replace(hour=am, minute=minute, second=0, microsecond=0)


def _due_from_period(text: str, now: datetime) -> datetime | None:
    if _TOMORROW_MORNING.search(text):
        return (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    if _TOMORROW_NIGHT.search(text):
        return (now + timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
    if _TONIGHT.search(text):
        return next_clock(8, now=now, meridiem="pm")
    if _AFTERNOON.search(text):
        return next_clock(3, now=now, meridiem="pm")
    if _THIS_MORNING.search(text):
        return next_clock(8, now=now, meridiem="am")
    if _TOMORROW.search(text):
        return (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    return None


def _period_meridiem(text: str) -> str | None:
    if _THIS_MORNING.search(text) or _TOMORROW_MORNING.search(text):
        return "am"
    if _TONIGHT.search(text) or _AFTERNOON.search(text) or _TOMORROW_NIGHT.search(text):
        return "pm"
    if re.search(r"\bmorning\b", text, re.IGNORECASE):
        return "am"
    if re.search(r"\b(?:evening|tonight|afternoon|night)\b", text, re.IGNORECASE):
        return "pm"
    return None


def _parse_hour(raw: Any) -> int | None:
    text = str(raw or "").strip().lower()
    if text in _HOUR_WORDS:
        return _HOUR_WORDS[text]
    if text.isdigit():
        hour = int(text)
        if 0 <= hour <= 23:
            return hour
    return None


def _meridiem(hit: re.Match[str]) -> str | None:
    for group in hit.groups()[2:]:
        text = str(group or "").lower().replace(".", "")
        if text.startswith("a"):
            return "am"
        if text.startswith("p"):
            return "pm"
    return None


def _next_at(now: datetime, hour: int, minute: int) -> datetime:
    hour = max(0, min(23, int(hour)))
    minute = max(0, min(59, int(minute)))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate > now:
        return candidate
    return candidate + timedelta(days=1)
