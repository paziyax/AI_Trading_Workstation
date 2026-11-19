"""Live and mock chat clients plus the shared error type and protocol.

The live client talks to OpenRouter through LiteLLM. Provider routing is left to
OpenRouter unless ``LLM_PROVIDER`` names one explicitly. Structured output is requested
with a strict hand-written JSON schema and the reply is parsed into
:class:`~app.llm.schemas.LLMResponse`.

Every failure mode the API layer can act on - missing key, transport error, empty reply,
invalid JSON, schema violation - is normalised to :class:`LLMError` so the API can answer
``503 {"detail": "AI assistant unavailable: ..."}`` without inspecting LiteLLM internals.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import litellm

from app.llm.config import LLMConfig
from app.llm.prompts import build_messages
from app.llm.schemas import RESPONSE_JSON_SCHEMA, LLMResponse

TEMPERATURE = 0.2
NUM_RETRIES = 1
REASONING_EFFORT = "low"
MAX_ERROR_DETAIL = 200


class LLMError(RuntimeError):
    """The assistant could not produce a usable structured response."""


@runtime_checkable
class ChatClient(Protocol):
    """Anything the API layer can call to get an assistant reply."""

    async def complete(
        self,
        *,
        user_message: str,
        context: str,
        portfolio: dict,
        history: list[tuple[str, str]],
    ) -> LLMResponse: ...


class LiveChatClient:
    """OpenRouter implementation of :class:`ChatClient`."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    async def complete(
        self,
        *,
        user_message: str,
        context: str,
        portfolio: dict,
        history: list[tuple[str, str]],
    ) -> LLMResponse:
        """Call the model and parse its structured reply.

        ``portfolio`` is accepted for interface parity: ``context`` (built by
        :func:`app.llm.prompts.build_context`) is the authoritative snapshot.
        """

        config = self._config
        if not config.api_key:
            raise LLMError("OPENROUTER_API_KEY is not configured")

        messages = build_messages(user_message=user_message, context=context, history=history)

        request: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "finally_chat",
                    "strict": True,
                    "schema": RESPONSE_JSON_SCHEMA,
                },
            },
            "api_key": config.api_key,
            "timeout": config.timeout,
            "num_retries": NUM_RETRIES,
            "temperature": TEMPERATURE,
            "reasoning_effort": REASONING_EFFORT,
        }
        if config.provider:
            # Opt-in pin only. Leaving LLM_PROVIDER empty lets OpenRouter route.
            request["extra_body"] = {
                "provider": {"order": [config.provider], "allow_fallbacks": True}
            }

        try:
            response = await litellm.acompletion(**request)
        except Exception as exc:
            raise LLMError(
                f"LLM request failed: {_describe(exc, config.api_key)}"
            ) from exc

        content = _content_of(response)
        if not content.strip():
            raise LLMError("LLM returned an empty response")

        try:
            return LLMResponse.model_validate_json(content)
        except Exception as exc:
            raise LLMError(
                f"LLM returned an invalid structured response: {_describe(exc, config.api_key)}"
            ) from exc


def create_chat_client(config: LLMConfig) -> ChatClient:
    """Return the mock client when ``config.mock`` is set, otherwise the live client."""

    if config.mock:
        from app.llm.mock import MockChatClient

        return MockChatClient()
    return LiveChatClient(config)


def _content_of(response: Any) -> str:
    """Extract assistant text from a LiteLLM response without trusting its shape."""

    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise LLMError("LLM response was malformed: no message content") from exc
    if content is None:
        return ""
    return content if isinstance(content, str) else str(content)


def _describe(exc: BaseException, api_key: str) -> str:
    """A short, secret-free description of a failure for the chat error payload."""

    detail = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    if api_key:
        detail = detail.replace(api_key, "[redacted]")
    detail = detail[:MAX_ERROR_DETAIL].strip()
    return detail or exc.__class__.__name__
