import sys

import os

from sonoscribe.scout.providers import (
    _anthropic,
    _aws_creds,
    _bedrock,
    _bedrock_bearer,
    _bedrock_client,
    _bedrock_model_id,
    _from_anthropic,
    _from_bedrock,
    _openai,
    _profile_candidates,
    _openai_messages,
    _to_anthropic_messages,
    _to_bedrock_messages,
    anthropic_tools,
    openai_tools,
)


def test_openai_and_anthropic_tool_shapes() -> None:
    names = {item["function"]["name"] for item in openai_tools()}
    assert names == {
        "search",
        "weather",
        "fetch",
        "open_page",
        "run_script",
        "write_file",
        "read_file",
        "capture_screen",
    }
    anth = {item["name"] for item in anthropic_tools()}
    assert anth == names


def test_provider_messages_carry_screen_image() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Current screen from capture_screen."},
                {"type": "image", "mime": "image/jpeg", "data": "Zm9v"},
            ],
        }
    ]
    openai = _openai_messages(messages)
    assert openai[0]["content"][1]["type"] == "image_url"
    assert openai[0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    _system, converted = _to_anthropic_messages(messages)
    assert converted[0]["content"][1]["type"] == "image"
    assert converted[0]["content"][1]["source"]["data"] == "Zm9v"
    bedrock = _to_bedrock_messages(converted)
    assert bedrock[0]["content"][1]["image"]["format"] == "jpeg"
    assert bedrock[0]["content"][1]["image"]["source"]["bytes"] == b"foo"


def test_from_anthropic_tool_use() -> None:
    reply = _from_anthropic(
        {
            "content": [
                {"type": "text", "text": "looking"},
                {"type": "tool_use", "id": "1", "name": "search", "input": {"query": "chicago"}},
            ]
        }
    )
    assert reply["content"] == "looking"
    assert reply["tool_calls"][0]["name"] == "search"
    assert reply["tool_calls"][0]["arguments"]["query"] == "chicago"


def test_openai_request_shape(monkeypatch) -> None:
    seen = {}

    def fake_post(url, payload, headers):
        seen["url"] = url
        seen["payload"] = payload
        seen["headers"] = headers
        return {"choices": [{"message": {"content": "ok", "tool_calls": []}}]}

    monkeypatch.setattr("sonoscribe.scout.providers._post_json", fake_post)
    reply = _openai(
        [{"role": "user", "content": "hi"}],
        {"model": "gpt-4o-mini"},
        "sk-test",
        "openai",
    )
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    assert seen["payload"]["model"] == "gpt-4o-mini"
    assert reply["content"] == "ok"


def test_openai_omits_tools_when_disallowed(monkeypatch) -> None:
    seen = {}

    def fake_post(url, payload, headers):
        seen["payload"] = payload
        return {"choices": [{"message": {"content": "ok", "tool_calls": []}}]}

    monkeypatch.setattr("sonoscribe.scout.providers._post_json", fake_post)
    _openai(
        [{"role": "user", "content": "hi"}],
        {"model": "gpt-4o-mini"},
        "sk-test",
        "openai",
        allow_tools=False,
    )
    assert "tools" not in seen["payload"]
    assert "tool_choice" not in seen["payload"]


def test_aws_creds_parse_access_secret_token() -> None:
    assert _aws_creds("AKIATEST:secret") == ("AKIATEST", "secret", "")
    assert _aws_creds("AKIATEST:secret:session") == ("AKIATEST", "secret", "session")
    assert _aws_creds("") == ("", "", "")
    assert _aws_creds("ABSKQmVkcm9ja0FQSUtleSexample==") == ("", "", "")
    assert _bedrock_bearer("ABSKQmVkcm9ja0FQSUtleSexample==") == "ABSKQmVkcm9ja0FQSUtleSexample=="
    assert _bedrock_bearer("AKIATEST:secret") == ""
    assert _bedrock_bearer("") == ""


def test_from_bedrock_tool_use() -> None:
    reply = _from_bedrock(
        {
            "output": {
                "message": {
                    "content": [
                        {"text": "looking"},
                        {"toolUse": {"toolUseId": "1", "name": "search", "input": {"query": "chicago"}}},
                    ]
                }
            }
        }
    )
    assert reply["content"] == "looking"
    assert reply["tool_calls"][0]["name"] == "search"
    assert reply["tool_calls"][0]["arguments"]["query"] == "chicago"


def test_bedrock_merges_parallel_tool_results() -> None:
    system, converted = _to_anthropic_messages(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "open google and search for foxes"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tooluse_A", "name": "search", "arguments": {"query": "foxes"}},
                    {"id": "tooluse_B", "name": "fetch", "arguments": {"url": "https://google.com"}},
                ],
            },
            {"role": "tool", "tool_call_id": "tooluse_A", "content": "hits"},
            {"role": "tool", "tool_call_id": "tooluse_B", "content": "page"},
        ]
    )
    assert system == "sys"
    assert converted[-1]["role"] == "user"
    results = converted[-1]["content"]
    assert [item["tool_use_id"] for item in results] == ["tooluse_A", "tooluse_B"]
    bedrock = _to_bedrock_messages(converted)
    last = bedrock[-1]["content"]
    assert last[0]["toolResult"]["toolUseId"] == "tooluse_A"
    assert last[1]["toolResult"]["toolUseId"] == "tooluse_B"
    assert bedrock[-2]["role"] == "assistant"
    assert {block["toolUse"]["toolUseId"] for block in bedrock[-2]["content"] if "toolUse" in block} == {
        "tooluse_A",
        "tooluse_B",
    }


def test_bedrock_uses_boto3(monkeypatch) -> None:
    seen = {}

    class FakeClient:
        def converse(self, **kwargs):
            seen.update(kwargs)
            return {
                "output": {
                    "message": {
                        "content": [{"text": "ok"}],
                    }
                }
            }

    monkeypatch.setattr("sonoscribe.scout.providers._bedrock_client", lambda region, key: FakeClient())
    reply = _bedrock(
        [{"role": "user", "content": "hi"}],
        {"bedrock_region": "us-west-2", "bedrock_model": "anthropic.claude-sonnet-4-20250514-v1:0"},
        "AKIATEST:secret",
    )
    assert seen["modelId"] == "us.anthropic.claude-sonnet-4-20250514-v1:0"
    assert seen["messages"][0]["role"] == "user"
    assert reply["content"] == "ok"


def test_bedrock_keeps_tool_config_when_history_has_tools(monkeypatch) -> None:
    seen = {}

    class FakeClient:
        def converse(self, **kwargs):
            seen.update(kwargs)
            return {"output": {"message": {"content": [{"text": "ok"}]}}}

    monkeypatch.setattr("sonoscribe.scout.providers._bedrock_client", lambda region, key: FakeClient())
    _bedrock(
        [
            {"role": "user", "content": "largest continent"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "tooluse_A", "name": "search", "arguments": {"query": "asia"}}],
            },
            {"role": "tool", "tool_call_id": "tooluse_A", "content": "Asia"},
        ],
        {"bedrock_region": "us-west-2", "bedrock_model": "anthropic.claude-sonnet-4-20250514-v1:0"},
        "AKIATEST:secret",
        allow_tools=False,
    )
    assert seen["toolConfig"]["tools"]
    assert "toolChoice" not in seen["toolConfig"]


def test_bedrock_omits_tool_config_when_disallowed_without_history(monkeypatch) -> None:
    seen = {}

    class FakeClient:
        def converse(self, **kwargs):
            seen.update(kwargs)
            return {"output": {"message": {"content": [{"text": "ok"}]}}}

    monkeypatch.setattr("sonoscribe.scout.providers._bedrock_client", lambda region, key: FakeClient())
    _bedrock(
        [{"role": "user", "content": "hi"}],
        {"bedrock_region": "us-west-2", "bedrock_model": "anthropic.claude-sonnet-4-20250514-v1:0"},
        "AKIATEST:secret",
        allow_tools=False,
    )
    assert "toolConfig" not in seen


def test_anthropic_keeps_tools_when_history_has_tools(monkeypatch) -> None:
    seen = {}

    def fake_post(url, payload, headers):
        seen["payload"] = payload
        return {"content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr("sonoscribe.scout.providers._post_json", fake_post)
    _anthropic(
        [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "1", "name": "search", "arguments": {"query": "hi"}}],
            },
            {"role": "tool", "tool_call_id": "1", "content": "hits"},
        ],
        {"model": "claude-sonnet-4-0"},
        "sk-ant",
        allow_tools=False,
    )
    assert seen["payload"]["tools"]
    assert seen["payload"]["tool_choice"] == {"type": "none"}


def test_bedrock_model_id_ignores_anthropic_api_names() -> None:
    default = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    assert _bedrock_model_id({"model": "claude-sonnet-4-0"}) == default
    assert _bedrock_model_id({"model": "gpt-4o-mini"}) == default
    assert (
        _bedrock_model_id({"bedrock_model": "us.anthropic.claude-sonnet-4-20250514-v1:0"})
        == "us.anthropic.claude-sonnet-4-20250514-v1:0"
    )
    assert (
        _bedrock_model_id({"model": "anthropic.claude-sonnet-4-20250514-v1:0"})
        == "anthropic.claude-sonnet-4-20250514-v1:0"
    )


def test_profile_candidates_prefix_foundation_ids() -> None:
    assert _profile_candidates("anthropic.claude-sonnet-5", "us-east-1")[0] == "us.anthropic.claude-sonnet-5"
    assert "global.anthropic.claude-sonnet-5" in _profile_candidates("anthropic.claude-sonnet-5", "us-east-1")
    assert _profile_candidates("global.anthropic.claude-opus-4-8", "us-east-1")[0] == (
        "global.anthropic.claude-opus-4-8"
    )
    assert _profile_candidates("eu.anthropic.claude-sonnet-5", "eu-west-1")[0] == "eu.anthropic.claude-sonnet-5"


def test_bedrock_api_key_sets_bearer_env(monkeypatch) -> None:
    seen = {}
    env = {}

    class FakeClient:
        def converse(self, **kwargs):
            seen.update(kwargs)
            env["converse"] = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
            return {"output": {"message": {"content": [{"text": "ok"}]}}}

    def fake_client(region, key):
        env["region"] = region
        env["key"] = key
        env["client"] = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
        return FakeClient()

    monkeypatch.setattr("sonoscribe.scout.providers._bedrock_client", fake_client)
    reply = _bedrock(
        [{"role": "user", "content": "hi"}],
        {"bedrock_region": "us-west-2", "bedrock_model": "anthropic.claude-sonnet-4-20250514-v1:0"},
        "ABSKQmVkcm9ja0FQSUtleSexample==",
    )
    assert env["key"] == ""
    assert env["client"] == "ABSKQmVkcm9ja0FQSUtleSexample=="
    assert env["converse"] == "ABSKQmVkcm9ja0FQSUtleSexample=="
    assert os.environ.get("AWS_BEARER_TOKEN_BEDROCK") != "ABSKQmVkcm9ja0FQSUtleSexample=="
    assert seen["modelId"] == "us.anthropic.claude-sonnet-4-20250514-v1:0"
    assert reply["content"] == "ok"


def test_bedrock_retries_inference_profile(monkeypatch) -> None:
    tried: list[str] = []

    class FakeClient:
        def converse(self, **kwargs):
            model_id = str(kwargs.get("modelId") or "")
            tried.append(model_id)
            if model_id.startswith("us."):
                raise RuntimeError(
                    "Invocation of model ID anthropic.claude-sonnet-5 with on-demand "
                    "throughput isn’t supported. Retry your request with the ID or ARN "
                    "of an inference profile that contains this model."
                )
            return {"output": {"message": {"content": [{"text": "ok"}]}}}

    monkeypatch.setattr("sonoscribe.scout.providers._bedrock_client", lambda region, key: FakeClient())
    reply = _bedrock(
        [{"role": "user", "content": "hi"}],
        {"bedrock_region": "us-east-1", "bedrock_model": "anthropic.claude-sonnet-5"},
        "AKIATEST:secret",
    )
    assert tried[0] == "us.anthropic.claude-sonnet-5"
    assert tried[1] == "global.anthropic.claude-sonnet-5"
    assert reply["content"] == "ok"


def test_bedrock_client_uses_key_or_default_chain(monkeypatch) -> None:
    seen = {}

    class FakeBoto:
        def client(self, name, **kwargs):
            seen["name"] = name
            seen["kwargs"] = kwargs
            return object()

    monkeypatch.setitem(sys.modules, "boto3", FakeBoto())
    _bedrock_client("eu-west-1", "AKIATEST:secret:session")
    assert seen["name"] == "bedrock-runtime"
    assert seen["kwargs"]["region_name"] == "eu-west-1"
    assert seen["kwargs"]["aws_access_key_id"] == "AKIATEST"
    assert seen["kwargs"]["aws_secret_access_key"] == "secret"
    assert seen["kwargs"]["aws_session_token"] == "session"

    seen.clear()
    _bedrock_client("us-east-1", "")
    assert seen["name"] == "bedrock-runtime"
    assert seen["kwargs"] == {"region_name": "us-east-1"}
