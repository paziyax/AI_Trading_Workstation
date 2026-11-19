---
name: openrouter-inference
description: Use this to write code that calls an LLM through OpenRouter with LiteLLM, including Strict Structured Outputs
---

# Calling an LLM via OpenRouter

These instructions show how to call a model through OpenRouter using LiteLLM.
This project uses DeepSeek V4.1 Flash 1017 by default.

## Setup

`OPENROUTER_API_KEY` must be set in the `.env` file and loaded as an environment variable.

The uv project must include litellm and pydantic:
```bash
uv add litellm pydantic
```

## Constants

```python
from litellm import completion

MODEL = "openrouter/deepseek/deepseek-v4.1-flash-1017"
```

Provider routing is left to OpenRouter. Do **not** send a provider order unless the
user explicitly asks to pin one. If a pin is ever needed, it is opt-in:

```python
# Optional only. Omit this for normal calls.
EXTRA_BODY = {"provider": {"order": ["deepseek"], "allow_fallbacks": True}}
```

## Plain text response

```python
response = completion(model=MODEL, messages=messages)
result = response.choices[0].message.content
```

Add `reasoning_effort="low"` only when the model supports reasoning controls.

## Strict Structured Outputs response

```python
response = completion(
    model=MODEL,
    messages=messages,
    response_format=MyBaseModelSubclass,
)
result = response.choices[0].message.content
result_as_object = MyBaseModelSubclass.model_validate_json(result)
```

Use `response_format={"type": "json_schema", "json_schema": {...}}` when you need a
hand-written strict schema instead of a pydantic class.

## Notes

- Any failure mode should be normalised into one project error type. See
  `backend/app/llm/client.py` for the reference implementation.
- Never log or echo the API key. Redact it from error messages.
