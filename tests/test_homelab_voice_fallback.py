"""Homelab: a voice turn always ends in something sayable.

A runaway model (hidden reasoning until max_tokens), a slow turn or a failing server must give a short
spoken apology, never the exception text, and the detail must reach the log.
"""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from openai import APIConnectionError

from custom_components.extended_openai_conversation import conversation as conv
from custom_components.extended_openai_conversation.const import (
    FALLBACK_ERROR_SPEECH,
    FALLBACK_SPEECH,
    FALLBACK_UNREACHABLE_SPEECH,
)
from custom_components.extended_openai_conversation.entity import (
    ExtendedOpenAIBaseLLMEntity,
)
from custom_components.extended_openai_conversation.exceptions import (
    TokenLengthExceededError,
)
from homeassistant.exceptions import HomeAssistantError


def _agent(handle_chat_log):
    return SimpleNamespace(
        subentry=SimpleNamespace(data={}),
        hass=MagicMock(),
        _get_exposed_entities=lambda: [],
        _get_function_tools=lambda: [],
        _build_system_prompt=lambda *args: "system",
        _async_handle_chat_log=handle_chat_log,
    )


async def _speech(handle_chat_log) -> tuple[str, str]:
    user_input = SimpleNamespace(
        text="Stop time, Matt.",
        language="en",
        conversation_id="c1",
        as_llm_context=lambda domain: None,
    )
    result = await conv.ExtendedOpenAIAgentEntity._async_handle_message(
        _agent(handle_chat_log), user_input, SimpleNamespace(content=[None])
    )
    response = result.response
    return response.response_type.value, response.speech["plain"]["speech"]


async def test_token_length_gives_the_fallback_not_the_exception(caplog) -> None:
    caplog.set_level(logging.WARNING)
    kind, speech = await _speech(AsyncMock(side_effect=TokenLengthExceededError(2048)))
    assert (kind, speech) == ("error", FALLBACK_SPEECH)
    assert "token length" not in speech
    assert "2048" in caplog.text


async def test_slow_turn_times_out_with_the_fallback(caplog) -> None:
    async def slow(*args, **kwargs):
        await asyncio.sleep(5)

    caplog.set_level(logging.WARNING)
    with patch.object(conv, "TURN_TIMEOUT", 0.05):
        kind, speech = await _speech(slow)
    assert (kind, speech) == ("error", FALLBACK_SPEECH)
    assert "No answer within" in caplog.text


async def test_unreachable_server_and_other_errors_are_spoken_plainly() -> None:
    err = APIConnectionError(request=httpx.Request("POST", "http://llm/v1"))
    assert await _speech(AsyncMock(side_effect=err)) == (
        "error",
        FALLBACK_UNREACHABLE_SPEECH,
    )
    boom = HomeAssistantError("tool exploded")
    assert await _speech(AsyncMock(side_effect=boom)) == (
        "error",
        FALLBACK_ERROR_SPEECH,
    )


def _chunk(finish_reason=None, content=None, reasoning=None):
    delta = SimpleNamespace(
        content=content, tool_calls=None, reasoning_content=reasoning
    )
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=None)


async def test_length_stop_logs_hidden_reasoning(caplog) -> None:
    async def stream():
        yield _chunk(reasoning="thinking " * 50)
        yield _chunk(finish_reason="length", reasoning="more")

    entity = SimpleNamespace(subentry=SimpleNamespace(data={"max_tokens": 2048}))
    caplog.set_level(logging.WARNING)
    try:
        async for _ in ExtendedOpenAIBaseLLMEntity._transform_stream(
            entity, MagicMock(), stream()
        ):
            pass
    except TokenLengthExceededError:
        pass
    else:
        raise AssertionError("length stop must still raise")
    assert "after 454 chars of hidden reasoning, 0 chars of text" in caplog.text


def _turn(*results):
    from custom_components.extended_openai_conversation.entity import (
        _make_tool_result_content,
    )
    from homeassistant.components import conversation as ha_conversation

    content = [ha_conversation.UserContent(content="Stop the timer.")]
    for i, data in enumerate(results):
        content.append(
            _make_tool_result_content(
                "conversation.x", f"c{i}", "echo_timer", {"result": data}
            )
        )
    content.append(
        ha_conversation.AssistantContent(agent_id="conversation.x", content="")
    )
    return SimpleNamespace(content=content)


def test_empty_reply_after_a_failed_tool_is_the_fallback(caplog) -> None:
    from custom_components.extended_openai_conversation.const import (
        SILENT_SUCCESS_SPEECH,
    )

    caplog.set_level(logging.WARNING)
    error = '{"error": "Invalid arguments: expected str", "retryable": false}'
    assert conv._empty_reply_speech(_turn(error, error), "x") == FALLBACK_SPEECH
    assert "last failed" in caplog.text
    ok = '{"status": "completed", "timers": []}'
    assert conv._empty_reply_speech(_turn(error, ok), "x") == SILENT_SUCCESS_SPEECH
    assert conv._empty_reply_speech(_turn(), "x") == FALLBACK_SPEECH
