"""Username the person chooses. Not taken from the Mac login."""

from __future__ import annotations

import re
from typing import Any

_USERNAME = re.compile(r"^[A-Za-z0-9._-]{2,40}$")


def clean_username(raw: Any) -> str:
    return str(raw or "").strip()[:40]


def usernames_match(left: Any, right: Any) -> bool:
    a = clean_username(left).casefold()
    b = clean_username(right).casefold()
    return bool(a) and a == b


def username_error(raw: Any) -> str | None:
    text = clean_username(raw)
    if not text:
        return "Username required."
    if " " in text:
        return "Username can't contain spaces."
    if not _USERNAME.fullmatch(text):
        return "Use 2-40 letters, numbers, dots, underscores, or hyphens."
    return None
