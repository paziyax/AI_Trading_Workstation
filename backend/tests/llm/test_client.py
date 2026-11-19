"""Live client behaviour with a fake ``litellm.acompletion`` (no network)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.llm.client import ChatClient, LiveChatClient, LLMError, create_chat_client
from app.llm.mock import MockChatClient
from app.llm.prompts import build_context
from app.llm.schemas import RESPONSE_JSON_SCHEMA
from tests.llm.conftest import make_config, payload


async def test_complete_sends_the_documented_request(
    fake_acompletion: Any,
    portfolio: dict[str, Any],
    watchlist: list[dict[str, Any]],
    recent_trades: list[dict[str, Any]],
) -> None:
    fake = fake_acompletion(content=payload())
    config = make_config()
    context = build_context(portfolio, watchlist, recent_trades)
    history = [("user", "earlier question"), ("assistant", "earlier answer")]

    await LiveChatClient(config).complete(
        user_message="Buy 5 AAPL", context=context, portfolio=portfolio, history=history
    )

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == "openrouter/openai/gpt-oss-120b"
    assert call["api_key"] == "test-key"
    assert call["timeout"] == 30.0
    assert call["num_retries"] == 1
    assert call["temperature"] == 0.2
    assert call["reasoning_effort"] == "low"
    assert call["extra_body"] == {"provider": {"order": ["cerebras"], "allow_fallbacks": True}}


async def test_complete_requests_the_strict_json_schema(fake_acompletion: Any) -> None:
    fake = fake_acompletion(content=payload())

    await LiveChatClient(make_config()).complete(
        user_message="hi", context="", portfolio={}, history=[]
    )

    response_format = fake.calls[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "finally_chat"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] is RESPONSE_JSON_SCHEMA


async def test_complete_uses_the_configured_model_provider_and_timeout(
    fake_acompletion: Any,
) -> None:
    fake = fake_acompletion(content=payload())
    config = make_config(
        model="openrouter/meta-llama/llama-3.3-70b-instruct", provider="groq", timeout=7.5
    )

    await LiveChatClient(config).complete(
        user_message="hi", context="", portfolio={}, history=[]
    )

    call = fake.calls[0]
    assert call["model"] == "openrouter/meta-llama/llama-3.3-70b-instruct"
    assert call["extra_body"] == {"provider": {"order": ["groq"], "allow_fallbacks": True}}
    assert call["timeout"] == 7.5


async def test_complete_builds_system_context_and_history_messages(
    fake_acompletion: Any, portfolio: dict[str, Any]
) -> None:
    fake = fake_acompletion(content=payload())
    context = build_context(portfolio, [], [])

    await LiveChatClient(make_config()).complete(
        user_message="How is my portfolio?",
        context=context,
        portfolio=portfolio,
        history=[("user", "hello"), ("assistant", "hi there")],
    )

    messages = fake.calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert "FinAlly" in messages[0]["content"]
    assert "- Cash: $8,100.00" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "hello"}
    assert messages[2] == {"role": "assistant", "content": "hi there"}
    assert messages[3] == {"role": "user", "content": "How is my portfolio?"}


async def test_complete_returns_the_parsed_response(fake_acompletion: Any) -> None:
    fake_acompletion(
        content=payload(
            message="Buying five shares.",
            trades=[{"ticker": "aapl", "side": "BUY", "quantity": 5}],
            watchlist_changes=[{"ticker": "pypl", "action": "add"}],
        )
    )

    response = await LiveChatClient(make_config()).complete(
        user_message="Buy 5 AAPL and add PYPL", context="", portfolio={}, history=[]
    )

    assert response.message == "Buying five shares."
    assert response.trades[0].ticker == "AAPL"
    assert response.trades[0].side == "buy"
    assert response.trades[0].quantity == 5.0
    assert response.watchlist_changes[0].ticker == "PYPL"
    assert response.watchlist_changes[0].action == "add"


async def test_missing_api_key_fails_before_the_network(fake_acompletion: Any) -> None:
    fake = fake_acompletion(content=payload())

    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        await LiveChatClient(make_config(api_key="")).complete(
            user_message="hi", context="", portfolio={}, history=[]
        )

    assert fake.calls == []


async def test_transport_errors_become_llm_errors(fake_acompletion: Any) -> None:
    fake_acompletion(error=RuntimeError("connection reset by peer"))

    with pytest.raises(LLMError, match="connection reset by peer"):
        await LiveChatClient(make_config()).complete(
            user_message="hi", context="", portfolio={}, history=[]
        )


async def test_transport_errors_never_leak_the_api_key(fake_acompletion: Any) -> None:
    fake_acompletion(error=RuntimeError("401 unauthorized: sk-or-secret-value"))

    with pytest.raises(LLMError) as excinfo:
        await LiveChatClient(make_config(api_key="sk-or-secret-value")).complete(
            user_message="hi", context="", portfolio={}, history=[]
        )

    assert "sk-or-secret-value" not in str(excinfo.value)
    assert "[redacted]" in str(excinfo.value)


@pytest.mark.parametrize("content", [None, "", "   ", "\n"])
async def test_empty_content_becomes_llm_error(fake_acompletion: Any, content: str | None) -> None:
    fake_acompletion(content=content)

    with pytest.raises(LLMError, match="empty response"):
        await LiveChatClient(make_config()).complete(
            user_message="hi", context="", portfolio={}, history=[]
        )


async def test_malformed_json_becomes_llm_error(fake_acompletion: Any) -> None:
    fake_acompletion(content="Sure, here is your answer in prose.")

    with pytest.raises(LLMError, match="invalid structured response"):
        await LiveChatClient(make_config()).complete(
            user_message="hi", context="", portfolio={}, history=[]
        )


async def test_schema_violation_becomes_llm_error(fake_acompletion: Any) -> None:
    fake_acompletion(
        content=payload(
            trades=[{"ticker": "AAPL", "side": "hold", "quantity": 5}],
        )
    )

    with pytest.raises(LLMError, match="invalid structured response"):
        await LiveChatClient(make_config()).complete(
            user_message="hi", context="", portfolio={}, history=[]
        )


async def test_response_without_choices_becomes_llm_error(fake_acompletion: Any) -> None:
    fake_acompletion(result=SimpleNamespace(choices=[]))

    with pytest.raises(LLMError, match="malformed"):
        await LiveChatClient(make_config()).complete(
            user_message="hi", context="", portfolio={}, history=[]
        )


async def test_response_without_a_message_becomes_llm_error(fake_acompletion: Any) -> None:
    fake_acompletion(result=SimpleNamespace(choices=[SimpleNamespace()]))

    with pytest.raises(LLMError, match="malformed"):
        await LiveChatClient(make_config()).complete(
            user_message="hi", context="", portfolio={}, history=[]
        )


async def test_error_details_are_truncated(fake_acompletion: Any) -> None:
    fake_acompletion(error=RuntimeError("x" * 500))

    with pytest.raises(LLMError) as excinfo:
        await LiveChatClient(make_config()).complete(
            user_message="hi", context="", portfolio={}, history=[]
        )

    assert len(str(excinfo.value)) < 300


def test_create_chat_client_returns_mock_when_configured() -> None:
    client = create_chat_client(make_config(mock=True))

    assert isinstance(client, MockChatClient)
    assert not isinstance(client, LiveChatClient)


def test_create_chat_client_returns_live_by_default() -> None:
    assert isinstance(create_chat_client(make_config()), LiveChatClient)


def test_both_clients_satisfy_the_protocol() -> None:
    assert isinstance(LiveChatClient(make_config()), ChatClient)
    assert isinstance(MockChatClient(), ChatClient)
