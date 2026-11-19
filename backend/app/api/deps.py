"""Request-time dependencies.

Every dependency is a plain attribute read from ``app.state``. The application factory puts
the objects there once, so routers never import globals and tests can swap a fake market
source or chat client without patching modules.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.db import Database
from app.llm import ChatClient, LLMConfig
from app.market import MarketDataSource, PriceCache
from app.services import SessionOpenTracker


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_database(request: Request) -> Database:
    return request.app.state.db


def get_cache(request: Request) -> PriceCache:
    return request.app.state.cache


def get_market_source(request: Request) -> MarketDataSource:
    return request.app.state.source


def get_chat_client(request: Request) -> ChatClient:
    return request.app.state.chat_client


def get_llm_config(request: Request) -> LLMConfig:
    return request.app.state.llm_config


def get_session_tracker(request: Request) -> SessionOpenTracker:
    return request.app.state.session_tracker


SettingsDep = Annotated[Settings, Depends(get_settings)]
DatabaseDep = Annotated[Database, Depends(get_database)]
CacheDep = Annotated[PriceCache, Depends(get_cache)]
MarketSourceDep = Annotated[MarketDataSource, Depends(get_market_source)]
ChatClientDep = Annotated[ChatClient, Depends(get_chat_client)]
LLMConfigDep = Annotated[LLMConfig, Depends(get_llm_config)]
SessionTrackerDep = Annotated[SessionOpenTracker, Depends(get_session_tracker)]
