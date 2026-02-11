from __future__ import annotations

import json
import logging

from openai import OpenAI

log = logging.getLogger(__name__)


def get_client() -> OpenAI:
    """Get an OpenAI client (uses OPENAI_API_KEY env var)."""
    return OpenAI()


def chat_json(client: OpenAI, model: str, system: str, user: str) -> dict | list:
    """Send a chat completion request and parse the response as JSON."""
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.7,
    )

    content = response.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        log.warning("Failed to parse LLM response as JSON: %s", content[:200])
        return {}


def chat_text(client: OpenAI, model: str, system: str, user: str) -> str:
    """Send a chat completion request and return raw text."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.7,
    )

    return response.choices[0].message.content or ""
