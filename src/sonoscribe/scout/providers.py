"""LLM HTTP adapters. Stdlib urllib, plus boto3 for Bedrock."""

from __future__ import annotations

import base64
import json
import os
from contextlib import contextmanager
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sonoscribe.scout.tools import TOOL_SPECS, active_tool_specs

SCOUT_PROVIDERS = ("openai", "anthropic", "grok", "kimi", "bedrock", "local")
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-0",
    "grok": "grok-3",
    "kimi": "moonshot-v1-auto",
    "bedrock": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "local": "llama3.2",
}
DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_BEDROCK_REGION = "us-east-1"
_OPENAI_BASE = {
    "openai": "https://api.openai.com/v1",
    "grok": "https://api.x.ai/v1",
    "kimi": "https://api.moonshot.ai/v1",
}
_TIMEOUT = 45


class ProviderError(RuntimeError):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


def openai_tools(specs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["schema"],
            },
        }
        for spec in (specs if specs is not None else TOOL_SPECS)
    ]


def anthropic_tools(specs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "name": spec["name"],
            "description": spec["description"],
            "input_schema": spec["schema"],
        }
        for spec in (specs if specs is not None else TOOL_SPECS)
    ]


def complete_chat(
    messages: list[dict[str, Any]],
    settings: dict[str, Any],
    key: str = "",
    allow_tools: bool = True,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    specs = tools if tools is not None else active_tool_specs(settings)
    provider = str(settings.get("provider") or "openai")
    if provider == "anthropic":
        return _with_retry(lambda: _anthropic(messages, settings, key, allow_tools=allow_tools, tools=specs))
    if provider == "bedrock":
        return _with_retry(lambda: _bedrock(messages, settings, key, allow_tools=allow_tools, tools=specs))
    return _with_retry(lambda: _openai(messages, settings, key, provider, allow_tools=allow_tools, tools=specs))


def _with_retry(fn):
    try:
        return fn()
    except ProviderError as exc:
        if exc.status != 429:
            raise
        return fn()


def _openai(
    messages: list[dict[str, Any]],
    settings: dict[str, Any],
    key: str,
    provider: str,
    allow_tools: bool = True,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    base = str(settings.get("base_url") or "").rstrip("/")
    if provider != "local":
        base = _OPENAI_BASE.get(provider, _OPENAI_BASE["openai"])
    elif not base:
        base = DEFAULT_BASE_URL
    model = str(settings.get("model") or DEFAULT_MODELS.get(provider) or "gpt-4o-mini")
    body: dict[str, Any] = {
        "model": model,
        "messages": _openai_messages(messages),
    }
    specs = tools if tools is not None else active_tool_specs(settings)
    if allow_tools and specs:
        body["tools"] = openai_tools(specs)
        body["tool_choice"] = "auto"
    elif specs and _history_has_tools(messages):
        body["tools"] = openai_tools(specs)
        body["tool_choice"] = "none"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = _post_json(f"{base}/chat/completions", body, headers)
    choice = ((data.get("choices") or [{}])[0]).get("message") or {}
    calls = []
    for item in choice.get("tool_calls") or []:
        fn = item.get("function") or {}
        args = fn.get("arguments") or "{}"
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}
        calls.append({"id": str(item.get("id") or ""), "name": str(fn.get("name") or ""), "arguments": args})
    inn, out = _usage_openai(data)
    return {"content": str(choice.get("content") or ""), "tool_calls": calls, "input_tokens": inn, "output_tokens": out}


def _anthropic(
    messages: list[dict[str, Any]],
    settings: dict[str, Any],
    key: str,
    allow_tools: bool = True,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    model = str(settings.get("model") or DEFAULT_MODELS["anthropic"])
    system, converted = _to_anthropic_messages(messages)
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": 2048,
        "system": system,
        "messages": converted,
    }
    specs = tools if tools is not None else active_tool_specs(settings)
    if allow_tools and specs:
        body["tools"] = anthropic_tools(specs)
    elif specs and _history_has_tools(messages):
        body["tools"] = anthropic_tools(specs)
        body["tool_choice"] = {"type": "none"}
    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    data = _post_json("https://api.anthropic.com/v1/messages", body, headers)
    return _from_anthropic(data)


def _bedrock(
    messages: list[dict[str, Any]],
    settings: dict[str, Any],
    key: str,
    allow_tools: bool = True,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    region = str(settings.get("bedrock_region") or DEFAULT_BEDROCK_REGION)
    model = _bedrock_model_id(settings)
    system, converted = _to_anthropic_messages(messages)
    payload: dict[str, Any] = {
        "messages": _to_bedrock_messages(converted),
        "inferenceConfig": {"maxTokens": 2048},
    }
    specs = tools if tools is not None else active_tool_specs(settings)
    if (allow_tools or _history_has_tools(messages)) and specs:
        payload["toolConfig"] = {"tools": [{"toolSpec": _bedrock_tool(spec)} for spec in specs]}
    if system:
        payload["system"] = [{"text": system}]
    token = _bedrock_bearer(key)
    try:
        if token:
            with _temporary_env("AWS_BEARER_TOKEN_BEDROCK", token):
                data = _bedrock_converse(_bedrock_client(region, ""), model, region, payload)
        else:
            data = _bedrock_converse(_bedrock_client(region, key), model, region, payload)
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(str(exc) or "Bedrock failed.") from exc
    if not isinstance(data, dict):
        data = dict(data) if data else {}
    return _from_bedrock(data)


def _bedrock_model_id(settings: dict[str, Any]) -> str:
    for raw in (settings.get("bedrock_model"), settings.get("model")):
        text = str(raw or "").strip()
        if _looks_like_bedrock_model(text):
            return text
    return DEFAULT_MODELS["bedrock"]


_FOUNDATION_PREFIXES = frozenset(
    {"anthropic", "amazon", "meta", "mistral", "cohere", "ai21", "stability"}
)
_PROFILE_PREFIXES = frozenset({"us", "eu", "apac", "au", "global"})


def _looks_like_bedrock_model(model: str) -> bool:
    text = str(model or "").strip()
    if text.startswith("arn:aws:bedrock:"):
        return True
    if "." not in text:
        return False
    return text.split(".", 1)[0] in _FOUNDATION_PREFIXES | _PROFILE_PREFIXES


def _foundation_model_id(model: str) -> str:
    text = str(model or "").strip()
    if not text or text.startswith("arn:"):
        return text
    head, _, rest = text.partition(".")
    if head in _PROFILE_PREFIXES and rest:
        return rest
    return text


def _profile_prefix_for_region(region: str) -> str:
    name = str(region or "").strip().lower()
    if name.startswith("eu-"):
        return "eu"
    if name in {"ap-southeast-2", "ap-southeast-4"}:
        return "au"
    if name.startswith("ap-"):
        return "apac"
    return "us"


def _profile_candidates(model: str, region: str) -> list[str]:
    text = str(model or "").strip()
    if not text or text.startswith("arn:"):
        return [text] if text else []
    foundation = _foundation_model_id(text)
    if foundation.split(".", 1)[0] not in _FOUNDATION_PREFIXES:
        return [text]
    out: list[str] = []
    if text.split(".", 1)[0] in _PROFILE_PREFIXES:
        out.append(text)
    for prefix in (_profile_prefix_for_region(region), "global", "us", "eu", "apac", "au"):
        candidate = f"{prefix}.{foundation}"
        if candidate not in out:
            out.append(candidate)
    return out


def _needs_inference_profile(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "inference profile" in text and "on-demand" in text


def _bedrock_converse(client, model: str, region: str, payload: dict[str, Any]) -> dict[str, Any]:
    last: Exception | None = None
    for model_id in _profile_candidates(model, region):
        try:
            return client.converse(modelId=model_id, **payload)
        except Exception as exc:
            last = exc
            if not _needs_inference_profile(exc):
                raise
    if last is not None:
        raise last
    raise ProviderError("Bedrock model is missing.")


@contextmanager
def _temporary_env(name: str, value: str):
    old = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


def _bedrock_client(region: str, key: str):
    try:
        import boto3
    except ImportError as exc:
        raise ProviderError("boto3 is not installed.") from exc
    kwargs: dict[str, Any] = {"region_name": region}
    access, secret, token = _aws_creds(key)
    if access and secret:
        kwargs["aws_access_key_id"] = access
        kwargs["aws_secret_access_key"] = secret
        if token:
            kwargs["aws_session_token"] = token
    return boto3.client("bedrock-runtime", **kwargs)


def _history_has_tools(messages: list[dict[str, Any]]) -> bool:
    return any(item.get("role") == "tool" or item.get("tool_calls") for item in messages)


def _usage_openai(data: dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usage") or {}
    return _as_int(usage.get("prompt_tokens")), _as_int(usage.get("completion_tokens"))


def _usage_anthropic(data: dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usage") or {}
    return _as_int(usage.get("input_tokens")), _as_int(usage.get("output_tokens"))


def _usage_bedrock(data: dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usage") or {}
    return _as_int(usage.get("inputTokens")), _as_int(usage.get("outputTokens"))


def _openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in messages:
        row = {
            key: item[key]
            for key in ("role", "content", "tool_calls", "tool_call_id", "name")
            if key in item
        }
        content = row.get("content")
        if isinstance(content, list):
            parts: list[dict[str, Any]] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                kind = str(part.get("type") or "")
                if kind == "text":
                    parts.append({"type": "text", "text": str(part.get("text") or "")})
                elif kind == "image" and part.get("data"):
                    mime = str(part.get("mime") or "image/jpeg")
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{part['data']}"},
                        }
                    )
            row["content"] = parts
        out.append(row)
    return out


def _image_bytes(raw: str) -> bytes:
    try:
        return base64.b64decode(raw, validate=False)
    except Exception:
        return b""


def _as_int(raw: Any) -> int:
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


def _bedrock_tool(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": spec["name"],
        "description": spec["description"],
        "inputSchema": {"json": spec["schema"]},
    }


def _to_anthropic_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system = ""
    out: list[dict[str, Any]] = []
    for item in messages:
        role = item.get("role")
        if role == "system":
            system = str(item.get("content") or "")
            continue
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": str(item.get("tool_call_id") or ""),
                "content": str(item.get("content") or ""),
            }
            prev = out[-1] if out else None
            parts = prev.get("content") if prev else None
            if (
                prev
                and prev.get("role") == "user"
                and isinstance(parts, list)
                and parts
                and all(isinstance(part, dict) and part.get("type") == "tool_result" for part in parts)
            ):
                parts.append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue
        if role == "assistant" and item.get("tool_calls"):
            blocks: list[dict[str, Any]] = []
            if item.get("content"):
                blocks.append({"type": "text", "text": str(item.get("content") or "")})
            for call in item.get("tool_calls") or []:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.get("id") or "",
                        "name": call.get("name") or "",
                        "input": call.get("arguments") or {},
                    }
                )
            out.append({"role": "assistant", "content": blocks})
            continue
        content = item.get("content")
        if isinstance(content, list):
            blocks = _anthropic_content_blocks(content)
            out.append({"role": role, "content": blocks or str(content)})
            continue
        out.append({"role": role, "content": str(content or "")})
    return system, out


def _anthropic_content_blocks(content: list[Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        kind = str(part.get("type") or "")
        if kind == "text":
            blocks.append({"type": "text", "text": str(part.get("text") or "")})
        elif kind == "image" and part.get("data"):
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": str(part.get("mime") or "image/jpeg"),
                        "data": str(part.get("data") or ""),
                    },
                }
            )
    return blocks


def _to_bedrock_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in messages:
        content = item.get("content")
        if isinstance(content, str):
            blocks = [{"text": content}]
        else:
            blocks = []
            for part in content or []:
                if part.get("type") == "text":
                    blocks.append({"text": part.get("text") or ""})
                elif part.get("type") == "tool_use":
                    blocks.append(
                        {
                            "toolUse": {
                                "toolUseId": part.get("id") or "",
                                "name": part.get("name") or "",
                                "input": part.get("input") or {},
                            }
                        }
                    )
                elif part.get("type") == "tool_result":
                    blocks.append(
                        {
                            "toolResult": {
                                "toolUseId": part.get("tool_use_id") or "",
                                "content": [{"text": str(part.get("content") or "")}],
                            }
                        }
                    )
                elif part.get("type") == "image":
                    source = part.get("source") if isinstance(part.get("source"), dict) else {}
                    data = str(part.get("data") or source.get("data") or "")
                    mime = str(part.get("mime") or source.get("media_type") or "image/jpeg")
                    raw = _image_bytes(data)
                    if raw:
                        fmt = "jpeg" if "jpeg" in mime else "png"
                        blocks.append({"image": {"format": fmt, "source": {"bytes": raw}}})
        out.append({"role": item.get("role"), "content": blocks})
    return out


def _from_anthropic(data: dict[str, Any]) -> dict[str, Any]:
    text = ""
    calls = []
    for item in data.get("content") or []:
        if item.get("type") == "text":
            text += str(item.get("text") or "")
        elif item.get("type") == "tool_use":
            args = item.get("input") or {}
            if not isinstance(args, dict):
                args = {}
            calls.append({"id": str(item.get("id") or ""), "name": str(item.get("name") or ""), "arguments": args})
    inn, out = _usage_anthropic(data)
    return {"content": text, "tool_calls": calls, "input_tokens": inn, "output_tokens": out}


def _from_bedrock(data: dict[str, Any]) -> dict[str, Any]:
    text = ""
    calls = []
    message = data.get("output") or data.get("message") or {}
    if isinstance(message, dict) and "message" in message:
        message = message.get("message") or {}
    for item in (message.get("content") or []):
        if "text" in item:
            text += str(item.get("text") or "")
        tool = item.get("toolUse") or {}
        if tool:
            args = tool.get("input") or {}
            if not isinstance(args, dict):
                args = {}
            calls.append(
                {
                    "id": str(tool.get("toolUseId") or ""),
                    "name": str(tool.get("name") or ""),
                    "arguments": args,
                }
            )
    inn, out = _usage_bedrock(data)
    return {"content": text, "tool_calls": calls, "input_tokens": inn, "output_tokens": out}


def _bedrock_bearer(key: str) -> str:
    text = str(key or "").strip()
    if not text:
        return ""
    access, secret, _token = _aws_creds(text)
    if access and secret:
        return ""
    return text


def _aws_creds(key: str) -> tuple[str, str, str]:
    text = str(key or "").strip()
    if not text or _looks_like_bedrock_key(text) or ":" not in text:
        return ("", "", "")
    parts = text.split(":", 2)
    access, secret = parts[0].strip(), parts[1].strip()
    if not access or not secret:
        return ("", "", "")
    return access, secret, parts[2].strip() if len(parts) > 2 else ""


def _looks_like_bedrock_key(text: str) -> bool:
    return text.startswith("ABSK") or text.startswith("bedrock-api-key-")


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=_TIMEOUT) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:240]
        except Exception:
            detail = ""
        raise ProviderError(detail or f"Provider failed ({exc.code}).", exc.code) from exc
    except URLError as exc:
        reason = str(getattr(exc, "reason", "") or exc)
        if "SSL" in reason.upper() or "CERTIFICATE" in reason.upper():
            raise ProviderError("Could not reach the model (TLS).") from exc
        raise ProviderError("Could not reach the model.") from exc
    except TimeoutError as exc:
        raise ProviderError("The model timed out.") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ProviderError("Provider returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise ProviderError("Provider returned invalid JSON.")
    return data
