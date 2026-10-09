"""Shared OpenAI helpers."""
from __future__ import annotations

import json
import os
import time

import openai
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
_client: OpenAI | None = None

# Network blips (connect timeouts, dropped connections, 5xx, rate limits) are retried with backoff.
RETRYABLE = (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError, openai.InternalServerError)


def get_client() -> OpenAI:
    global _client
    if _client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY missing - add it to the .env file")
        # Short connect timeout so a dead connection fails fast and is retried, long read timeout for big prompts.
        _client = OpenAI(api_key=key, max_retries=0, timeout=openai.Timeout(180, connect=15))
    return _client


def with_retry(call, attempts: int = 5):
    for i in range(attempts):
        try:
            return call()
        except RETRYABLE as e:
            if i == attempts - 1:
                raise RuntimeError("Could not reach OpenAI (network connection problem). "
                                   "Check your internet connection and try again.") from e
            time.sleep(min(20, 2 * 2 ** i))


def model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o")


def classify_model() -> str:
    """Model for competitor classification: a reasoning model follows the relevance rules far more consistently."""
    return os.getenv("OPENAI_CLASSIFY_MODEL", "gpt-5.4-mini")


def chat_json(messages: list, temperature: float = 0.3, model_name: str | None = None) -> dict:
    name = model_name or model()
    # Reasoning models (gpt-5*, o-series) only accept the default temperature.
    extra = {} if name.startswith(("gpt-5", "o1", "o3", "o4")) else {"temperature": temperature}
    resp = with_retry(lambda: get_client().chat.completions.create(
        model=name, messages=messages, response_format={"type": "json_object"}, **extra,
    ))
    return json.loads(resp.choices[0].message.content)
