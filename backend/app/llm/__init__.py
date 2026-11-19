"""Public surface of the FinAlly LLM package.

Only the names below are part of the contract with the API layer.
"""

from app.llm.client import ChatClient, LiveChatClient, LLMError, create_chat_client
from app.llm.config import LLMConfig
from app.llm.mock import MockChatClient
from app.llm.prompts import build_context
from app.llm.schemas import LLMResponse, TradeAction, WatchlistChange

__all__ = [
    "ChatClient",
    "LLMConfig",
    "LLMError",
    "LLMResponse",
    "LiveChatClient",
    "MockChatClient",
    "TradeAction",
    "WatchlistChange",
    "build_context",
    "create_chat_client",
]
