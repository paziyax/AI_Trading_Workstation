"""Environment parsing for :class:`app.llm.config.LLMConfig`."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.llm.config import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_TIMEOUT_SECONDS,
    LLMConfig,
)


def test_defaults_with_empty_environment() -> None:
    config = LLMConfig.from_env({})

    assert config.mock is False
    assert config.api_key == ""
    assert config.model == "openrouter/deepseek/deepseek-v4.1-flash-1017"
    assert config.model == DEFAULT_MODEL
    assert config.provider == DEFAULT_PROVIDER == ""
    assert config.timeout == DEFAULT_TIMEOUT_SECONDS == 30.0


def test_documented_variables_are_read() -> None:
    config = LLMConfig.from_env(
        {
            "OPENROUTER_API_KEY": "  sk-or-test  ",
            "LLM_MOCK": "true",
            "LLM_MODEL": "openrouter/meta-llama/llama-3.3-70b-instruct",
            "LLM_PROVIDER": "Groq",
            "LLM_TIMEOUT_SECONDS": "12.5",
        }
    )

    assert config.mock is True
    assert config.api_key == "sk-or-test"
    assert config.model == "openrouter/meta-llama/llama-3.3-70b-instruct"
    assert config.provider == "groq"
    assert config.timeout == 12.5


@pytest.mark.parametrize("value", ["true", "TRUE", "True", "1", "yes", "on"])
def test_truthy_mock_values(value: str) -> None:
    assert LLMConfig.from_env({"LLM_MOCK": value}).mock is True


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off", "maybe", ""])
def test_non_truthy_mock_values(value: str) -> None:
    assert LLMConfig.from_env({"LLM_MOCK": value}).mock is False


def test_blank_optional_values_fall_back_to_defaults() -> None:
    config = LLMConfig.from_env(
        {
            "OPENROUTER_API_KEY": "   ",
            "LLM_MODEL": "   ",
            "LLM_PROVIDER": "  ",
            "LLM_TIMEOUT_SECONDS": "   ",
        }
    )

    assert config.api_key == ""
    assert config.model == DEFAULT_MODEL
    assert config.provider == DEFAULT_PROVIDER
    assert config.timeout == DEFAULT_TIMEOUT_SECONDS


@pytest.mark.parametrize("value", ["soon", "30s", "0", "-5", "nan", "inf"])
def test_invalid_or_non_positive_timeout_falls_back(value: str) -> None:
    assert LLMConfig.from_env({"LLM_TIMEOUT_SECONDS": value}).timeout == 30.0


def test_missing_api_key_does_not_raise() -> None:
    config = LLMConfig.from_env({"LLM_MOCK": "false"})

    assert config.api_key == ""
    assert config.mock is False


def test_from_env_reads_os_environ_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "openrouter/meta-llama/llama-3.3-70b-instruct")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_MOCK", "1")

    config = LLMConfig.from_env()

    assert config.model == "openrouter/meta-llama/llama-3.3-70b-instruct"
    assert config.provider == "groq"
    assert config.mock is True


def test_config_is_frozen() -> None:
    config = LLMConfig.from_env({})

    with pytest.raises(FrozenInstanceError):
        config.mock = True  # type: ignore[misc]
