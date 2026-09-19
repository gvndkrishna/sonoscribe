"""Validate the structured task answer before the UI sees it."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

_BLOCK_TYPES = ("lead", "facts", "list", "code", "note", "links", "error")
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def parse_answer(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        recovered = _recover_embedded_json(raw)
        return clean_answer(recovered if recovered is not None else raw)
    text = str(raw or "").strip()
    if not text:
        return _lead("No answer.")
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = _decode_json(text)
    if isinstance(data, dict):
        return clean_answer(data)
    if _looks_like_brief_json(text):
        return _lead("The model returned a broken brief. Try a follow-up.")
    return _lead(text)


def _looks_like_brief_json(text: str) -> bool:
    body = text.lstrip()
    return body.startswith("{") and '"blocks"' in body


def _recover_embedded_json(raw: dict[str, Any]) -> dict[str, Any] | None:
    blocks = raw.get("blocks")
    if not isinstance(blocks, list) or len(blocks) != 1:
        return None
    block = blocks[0]
    if not isinstance(block, dict) or str(block.get("type") or "") != "lead":
        return None
    text = str(block.get("text") or "").strip()
    if not _looks_like_brief_json(text):
        return None
    data = _decode_json(text)
    if not isinstance(data, dict) or not isinstance(data.get("blocks"), list):
        return None
    if len(data["blocks"]) == 1 and data["blocks"] == blocks:
        return None
    return data


def _decode_json(text: str) -> Any:
    body = str(text or "").strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    start = min((index for index in (body.find("{"), body.find("[")) if index >= 0), default=-1)
    if start < 0:
        return None
    snippet = body[start:]
    try:
        data, _end = json.JSONDecoder().raw_decode(snippet)
        return data
    except json.JSONDecodeError:
        pass
    repaired = _repair_json(snippet)
    if not repaired:
        return None
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


def _repair_json(text: str) -> str:
    out: list[str] = []
    stack: list[str] = []
    in_str = False
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
            out.append(ch)
            i += 1
            continue
        if ch in "}]":
            while out and out[-1] in " \t\n\r":
                out.pop()
            if out and out[-1] == ",":
                out.pop()
            if not stack:
                i += 1
                continue
            expected = stack[-1]
            if ch != expected:
                out.append(expected)
                stack.pop()
                continue
            stack.pop()
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    if in_str:
        if escape:
            out.append(" ")
        out.append('"')
    while stack:
        out.append(stack.pop())
    return "".join(out)


_BLURB_WORDS = 8
_BLURB_CHARS = 56
_BLURB_SKIP = frozenset({"no answer", "failed"})


def clean_blurb(raw: Any, *, words: int = _BLURB_WORDS, chars: int = _BLURB_CHARS) -> str:
    text = " ".join(str(raw or "").split()).strip().rstrip(".,;:!")
    if not text:
        return ""
    limit = max(1, int(words or _BLURB_WORDS))
    width = max(8, int(chars or _BLURB_CHARS))
    text = " ".join(text.split()[:limit])
    if len(text) > width:
        text = text[:width].rsplit(" ", 1)[0] or text[:width]
    return text


def _blurb_budget(data: dict[str, Any]) -> tuple[int, int]:
    blocks = [item for item in (data.get("blocks") or []) if isinstance(item, dict)]
    lead_words = 0
    extras = 0
    for block in blocks:
        kind = str(block.get("type") or "")
        if kind in {"lead", "error", "note"}:
            count = len(str(block.get("text") or "").split())
            if kind == "lead" and not lead_words:
                lead_words = count
            elif kind != "lead":
                extras += 1
        elif kind in {"facts", "list", "links", "code"}:
            extras += 1
    if extras >= 2 or lead_words >= 20:
        return _BLURB_WORDS, _BLURB_CHARS
    if extras >= 1 or lead_words >= 10:
        return 6, 48
    return 5, 40


def answer_blurb(answer: Any) -> str:
    data = answer if isinstance(answer, dict) else {}
    blurb = clean_blurb(data.get("blurb"))
    if blurb:
        return blurb
    words, chars = _blurb_budget(data)
    for block in data.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        if str(block.get("type") or "") not in {"lead", "error", "note"}:
            continue
        text = str(block.get("text") or "").strip()
        if text and text.casefold().rstrip(".,;:!") not in _BLURB_SKIP:
            return clean_blurb(text, words=words, chars=chars)
    return clean_blurb(data.get("title"), words=words, chars=chars)


def clean_answer(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    kind = str(data.get("kind") or "qa").strip() or "qa"
    title = str(data.get("title") or "").strip()[:160]
    blocks = _clean_blocks(data.get("blocks"))
    if not blocks:
        text = str(data.get("text") or data.get("message") or "").strip()
        blocks = [_block("lead", text)] if text else [_block("error", "No answer.")]
    blurb = answer_blurb({"blurb": data.get("blurb"), "title": title, "blocks": blocks})
    insert = str(data.get("insert") or "").strip()[:4000]
    out = {"kind": kind, "title": title, "blurb": blurb, "blocks": blocks}
    if insert:
        out["insert"] = insert
    return out


def error_answer(message: str, title: str = "") -> dict[str, Any]:
    text = str(message or "").strip()
    return {
        "kind": "error",
        "title": str(title or "").strip()[:160],
        "blurb": clean_blurb(text) or "failed",
        "blocks": [_block("error", text or "failed")],
    }


def _lead(text: str) -> dict[str, Any]:
    body = str(text or "").strip() or "No answer."
    return {"kind": "qa", "title": "", "blurb": clean_blurb(body), "blocks": [_block("lead", body)]}


def _clean_blocks(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip()
        if kind not in _BLOCK_TYPES:
            continue
        if kind == "facts":
            rows = []
            for row in item.get("rows") or []:
                if isinstance(row, (list, tuple)) and len(row) >= 2:
                    left = str(row[0] or "").strip()[:80]
                    right = str(row[1] or "").strip()[:240]
                    if left or right:
                        rows.append([left, right])
            if rows:
                out.append({"type": "facts", "rows": rows[:16]})
            continue
        if kind == "list":
            items = [str(value).strip()[:240] for value in (item.get("items") or []) if str(value).strip()]
            if items:
                out.append({"type": "list", "items": items[:20]})
            continue
        if kind == "links":
            links = []
            for link in item.get("items") or []:
                if not isinstance(link, dict):
                    continue
                label = str(link.get("label") or "").strip()[:80]
                url = _http_url(link.get("url"))
                if url:
                    links.append({"label": label or url, "url": url})
            if links:
                out.append({"type": "links", "items": links[:12]})
            continue
        text = str(item.get("text") or "").strip()
        if text:
            out.append(_block(kind, text))
    return out[:12]


def _block(kind: str, text: str) -> dict[str, Any]:
    limit = 4000 if kind == "code" else 1200
    return {"type": kind, "text": text[:limit]}


def _http_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def answer_plain(answer: Any, limit: int = 1600) -> str:
    data = answer if isinstance(answer, dict) else {}
    parts: list[str] = []
    for block in data.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        kind = str(block.get("type") or "")
        if kind in {"lead", "note", "error", "code"}:
            text = str(block.get("text") or "").strip()
            if text:
                parts.append(text)
        elif kind == "list":
            parts.extend(str(value).strip() for value in (block.get("items") or []) if str(value).strip())
        elif kind == "facts":
            for row in block.get("rows") or []:
                if isinstance(row, (list, tuple)) and len(row) >= 2:
                    left = str(row[0] or "").strip()
                    right = str(row[1] or "").strip()
                    if left or right:
                        parts.append(f"{left}: {right}".strip(": "))
        elif kind == "links":
            for link in block.get("items") or []:
                if isinstance(link, dict) and link.get("url"):
                    parts.append(str(link.get("label") or link.get("url") or "").strip())
        if sum(len(part) for part in parts) >= limit:
            break
    return "\n".join(part for part in parts if part).strip()[:limit]
