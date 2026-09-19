from io import BytesIO

from sonoscribe.scout.cost import estimate_cost
from sonoscribe.scout.mcp import encode_stdio_message, mcp_tool_name, parse_mcp_name, read_stdio_message


def test_estimate_cost_gpt4o_mini() -> None:
    cost = estimate_cost("gpt-4o-mini", 1_000_000, 0)
    assert cost == 0.15
    assert estimate_cost("local-llama", 1000, 1000) == 0.0


def test_mcp_tool_name_is_safe() -> None:
    name = mcp_tool_name("mcp-ab12", "list/repos")
    assert name.startswith("mcp_")
    assert "/" not in name
    parsed = parse_mcp_name(name)
    assert parsed is not None


def test_stdio_framing_roundtrip() -> None:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    framed = encode_stdio_message(payload)
    assert framed.startswith(b"Content-Length:")
    parsed = read_stdio_message(BytesIO(framed), deadline=10**12)
    assert parsed["id"] == 1
    ndjson = BytesIO(b'{"jsonrpc":"2.0","id":2}\n')
    assert read_stdio_message(ndjson, deadline=10**12)["id"] == 2
