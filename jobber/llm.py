"""Thin wrapper around the Anthropic Claude API used by ranking + tailoring."""
from __future__ import annotations

import json
import re

from . import config

# Cheap + fast model for scoring many jobs; stronger model for writing.
RANK_MODEL = "claude-haiku-4-5-20251001"
WRITE_MODEL = "claude-sonnet-4-6"

_client = None


def client():
    global _client
    if _client is None:
        import anthropic
        key = config.env("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _client = anthropic.Anthropic(api_key=key)
    return _client


def _system_blocks(system, cache: bool):
    if not system:
        return None
    blocks = [{"type": "text", "text": system}] if isinstance(system, str) else list(system)
    if cache and blocks:
        blocks = [dict(b) for b in blocks]
        blocks[-1]["cache_control"] = {"type": "ephemeral"}  # reuse big resume across calls
    return blocks


def complete(prompt: str, *, system=None, model: str = WRITE_MODEL,
             max_tokens: int = 1500, temperature: float = 0.4,
             cache_system: bool = False) -> str:
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    blocks = _system_blocks(system, cache_system)
    if blocks:
        kwargs["system"] = blocks
    msg = client().messages.create(**kwargs)
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


def complete_json(prompt: str, **kwargs):
    """Like complete(), but parse the model's reply as JSON."""
    kwargs.setdefault("model", RANK_MODEL)
    kwargs.setdefault("temperature", 0.0)
    return _extract_json(complete(prompt, **kwargs))


def _extract_json(text: str):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = text.find(opener), text.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except Exception:
                continue
    raise ValueError(f"Could not parse JSON from model reply: {text[:200]}")
