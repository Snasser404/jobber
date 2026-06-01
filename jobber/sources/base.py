"""Shared helpers for job sources: HTTP, HTML cleanup, keyword matching."""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Jobber/0.1 (personal job-search assistant)"


def http_get(url: str, params: dict | None = None, headers: dict | None = None,
             timeout: int = 20) -> requests.Response:
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        h.update(headers)
    r = requests.get(url, params=params, headers=h, timeout=timeout)
    r.raise_for_status()
    return r


def html_to_text(html: str) -> str:
    """Convert an HTML job description to readable plain text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    out: list[str] = []
    blank = False
    for raw in text.splitlines():
        ln = raw.strip()
        if ln:
            out.append(ln)
            blank = False
        elif not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()


_STOP = {"specialist", "performance", "senior", "junior", "lead", "manager", "and"}


def keyword_tokens(keywords: list[str]) -> set[str]:
    """Break search phrases into the significant single words to match on."""
    tokens: set[str] = set()
    for kw in keywords or []:
        for word in kw.lower().replace("/", " ").split():
            if len(word) >= 3 and word not in _STOP:
                tokens.add(word)
    return tokens


def text_matches(text: str, tokens: set[str]) -> bool:
    """True if any significant keyword token appears in the text."""
    if not tokens:
        return True
    low = (text or "").lower()
    return any(tok in low for tok in tokens)


def looks_remote(*parts: str) -> bool:
    return "remote" in " ".join(p or "" for p in parts).lower()
