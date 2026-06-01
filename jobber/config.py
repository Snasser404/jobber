"""Load configuration (config.yaml) and secrets (.env)."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Project root = folder that contains this package
ROOT = Path(__file__).resolve().parent.parent

# Load .env (if present) into the environment.
# override=True so your .env wins over a stale/empty shell variable of the same name.
load_dotenv(ROOT / ".env", override=True)


def load_config(path: str | Path | None = None) -> dict:
    """Read config.yaml into a plain dict."""
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def env(name: str, default: str = "") -> str:
    """Read a setting from the OS/.env, falling back to Streamlit secrets (cloud)."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return default


def is_cloud() -> bool:
    """True when hosted on a server (set JOBBER_CLOUD=1 in the host's secrets)."""
    return bool(env("JOBBER_CLOUD"))


def has_anthropic_key() -> bool:
    return bool(env("ANTHROPIC_API_KEY"))


def has_adzuna_keys() -> bool:
    return bool(env("ADZUNA_APP_ID") and env("ADZUNA_APP_KEY"))


def abspath(relative: str | Path) -> Path:
    """Resolve a path from config relative to the project root."""
    p = Path(relative)
    return p if p.is_absolute() else (ROOT / p)
