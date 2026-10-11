"""Guards for the homelab fork's own changes (upstream PR #446 and local fixes).

If an upstream merge breaks these, the sync PR fails CI instead of breaking voice.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import voluptuous as vol

from custom_components.extended_openai_conversation.entity import (
    ExtendedOpenAIBaseLLMEntity,
    _adjust_schema,
    _make_nullable_optional,
    _tool_result_data,
)
from homeassistant.helpers import llm


async def _run_llm_api_tool(returned) -> dict:
    llm_api = SimpleNamespace(async_call_tool=AsyncMock(return_value=returned))
    entity = SimpleNamespace(entity_id="conversation.test")
    tool_input = llm.ToolInput(tool_name="echo_show", tool_args={}, id="call_1")
    content = await ExtendedOpenAIBaseLLMEntity._execute_function_tool(
        entity,
        SimpleNamespace(llm_api=llm_api),
        {"function": {"type": "llm_api", "tool_name": "echo_show"}},
        tool_input,
        None,
        [],
    )
    assert content.tool_call_id == "call_1"
    assert content.tool_name == "echo_show"
    return _tool_result_data(content)


async def test_llm_api_tool_returning_dict() -> None:
    """Older tools return a plain dict."""
    data = await _run_llm_api_tool({"ok": True})
    assert json.loads(data["result"]) == {"ok": True}


async def test_llm_api_tool_returning_tool_result() -> None:
    """Home Assistant 2026.10+ wraps tool output in llm.ToolResult."""
    if not hasattr(llm, "ToolResult"):
        return
    data = await _run_llm_api_tool(llm.ToolResult(data={"ok": True}))
    assert json.loads(data["result"]) == {"ok": True}


def test_llm_api_tools_listed() -> None:
    """HA LLM API tools are offered to the model with an OpenAI-compatible schema."""
    tool = SimpleNamespace(
        name="echo_show",
        description="Show a view",
        parameters=vol.Schema({vol.Required("view"): str}),
    )
    llm_api = SimpleNamespace(
        tools=[tool], custom_serializer=None, api=SimpleNamespace(id="assist")
    )
    [listed] = ExtendedOpenAIBaseLLMEntity._convert_llm_api_tools(None, llm_api)
    assert listed["function"] == {"type": "llm_api", "tool_name": "echo_show"}
    assert listed["spec"]["parameters"]["properties"]["view"]["type"] == "string"


def test_schema_helpers_tolerate_unconvertible_fragments() -> None:
    """Fragments the converter can't express must not crash schema adjustment."""
    marker = object()
    schema = {"type": "object", "properties": {"odd": marker}, "required": []}
    _adjust_schema(schema)
    _make_nullable_optional(schema)
    _adjust_schema(marker)
    _make_nullable_optional(marker)
