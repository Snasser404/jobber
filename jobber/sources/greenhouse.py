"""Greenhouse — pull jobs straight from a company's careers board. No key."""
from __future__ import annotations

from .base import http_get, html_to_text, keyword_tokens, text_matches, looks_remote
from ..models import Job


def fetch(cfg: dict) -> list[Job]:
    tokens_cfg = ((cfg.get("ats", {}) or {}).get("greenhouse", []) or [])
    kw_tokens = keyword_tokens((cfg.get("search", {}) or {}).get("keywords", []))
    jobs: list[Job] = []
    for company in tokens_cfg:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
        try:
            data = http_get(url, params={"content": "true"}).json().get("jobs", [])
        except Exception:
            continue
        for j in data:
            content = j.get("content", "")
            blob = f"{j.get('title','')} {content}"
            if not text_matches(blob, kw_tokens):
                continue
            loc = (j.get("location") or {}).get("name", "")
            jobs.append(Job(
                source=f"greenhouse:{company}",
                title=j.get("title", ""),
                company=company.replace("-", " ").title(),
                location=loc,
                url=j.get("absolute_url", ""),
                apply_url=j.get("absolute_url", ""),
                description=html_to_text(content),
                remote=looks_remote(loc, j.get("title", "")),
                posted_at=j.get("updated_at", "") or "",
                raw=j,
            ))
    return jobs
