"""Pluggable LLM layer.

Works with Claude (Anthropic) OR any OpenAI-compatible API — DeepSeek, OpenRouter
(free DeepSeek/Qwen/Llama), Google Gemini, Groq, Together, local Ollama, etc.

Pick a provider with env vars (see .env.example):
  • Claude (default):  ANTHROPIC_API_KEY
  • Anything else:     LLM_PROVIDER=openai, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
"""
from __future__ import annotations

import json
import re

from . import config

_ANTHROPIC_RANK = "claude-haiku-4-5-20251001"
_ANTHROPIC_WRITE = "claude-sonnet-4-6"

_client_cache = None
_client_provider = None


def provider() -> str:
    """Which backend to use. Explicit LLM_PROVIDER wins; else Claude, unless this app
    is explicitly pointed at an OpenAI-compatible provider via LLM_API_KEY/LLM_BASE_URL."""
    p = config.env("LLM_PROVIDER").lower().strip()
    if p:
        return p
    if config.env("LLM_API_KEY") or config.env("LLM_BASE_URL"):
        return "openai"          # this app was pointed at a cheap/free provider
    if config.env("ANTHROPIC_API_KEY"):
        return "anthropic"
    if config.env("OPENAI_API_KEY"):
        return "openai"
    return "anthropic"


def is_configured() -> bool:
    if provider() == "anthropic":
        return bool(config.env("ANTHROPIC_API_KEY"))
    return bool(config.env("LLM_API_KEY") or config.env("OPENAI_API_KEY"))


def label() -> str:
    """Human-friendly name of the active model/provider, for the UI."""
    if provider() == "anthropic":
        return "Claude"
    base = (config.env("LLM_BASE_URL") or "").lower()
    for needle, name in (("openrouter", "OpenRouter"), ("deepseek", "DeepSeek"),
                         ("groq", "Groq"), ("googleapis", "Gemini"), ("together", "Together")):
        if needle in base:
            return name
    return config.env("LLM_MODEL") or "custom model"


def rank_model() -> str:
    if provider() == "anthropic":
        return config.env("LLM_RANK_MODEL") or _ANTHROPIC_RANK
    return (config.env("LLM_RANK_MODEL") or config.env("LLM_MODEL")
            or config.env("LLM_WRITE_MODEL") or "gpt-4o-mini")


def write_model() -> str:
    if provider() == "anthropic":
        return config.env("LLM_WRITE_MODEL") or _ANTHROPIC_WRITE
    return (config.env("LLM_WRITE_MODEL") or config.env("LLM_MODEL")
            or "gpt-4o-mini")


def _client():
    global _client_cache, _client_provider
    prov = provider()
    if _client_cache is not None and _client_provider == prov:
        return prov, _client_cache
    if prov == "anthropic":
        import anthropic
        key = config.env("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("No ANTHROPIC_API_KEY set. Add it to .env / secrets.")
        _client_cache = anthropic.Anthropic(api_key=key)
    else:
        from openai import OpenAI
        key = config.env("LLM_API_KEY") or config.env("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("No LLM_API_KEY set for the OpenAI-compatible provider.")
        base = config.env("LLM_BASE_URL")
        _client_cache = OpenAI(api_key=key, base_url=base) if base else OpenAI(api_key=key)
    _client_provider = prov
    return prov, _client_cache


def complete(prompt: str, *, system=None, role: str = "write", model: str | None = None,
             max_tokens: int = 1500, temperature: float = 0.4,
             cache_system: bool = False) -> str:
    prov, client = _client()
    model = model or (rank_model() if role == "rank" else write_model())

    if prov == "anthropic":
        blocks = None
        if system:
            blocks = [{"type": "text", "text": system}]
            if cache_system:
                blocks[-1]["cache_control"] = {"type": "ephemeral"}
        kwargs = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                  "messages": [{"role": "user", "content": prompt}]}
        if blocks:
            kwargs["system"] = blocks
        msg = client.messages.create(**kwargs)
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()

    # OpenAI-compatible chat completions
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(
        model=model, messages=messages, max_tokens=max_tokens, temperature=temperature)
    return (resp.choices[0].message.content or "").strip()


def complete_json(prompt: str, **kwargs):
    kwargs.setdefault("role", "rank")
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
