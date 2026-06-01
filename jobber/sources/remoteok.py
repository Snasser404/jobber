"""RemoteOK — free remote-jobs API, no key required."""
from __future__ import annotations

from .base import http_get, html_to_text, keyword_tokens, text_matches
from ..models import Job

API = "https://remoteok.com/api"


def _salary(j: dict) -> str:
    lo, hi = j.get("salary_min"), j.get("salary_max")
    if lo and hi:
        return f"${int(lo):,} - ${int(hi):,}"
    return ""


def fetch(cfg: dict) -> list[Job]:
    search = cfg.get("search", {}) or {}
    if not search.get("remote_ok", True):
        return []
    limit = int(search.get("max_results_per_source", 25))
    tokens = keyword_tokens(search.get("keywords", []))
    try:
        data = http_get(API).json()
    except Exception:
        return []
    jobs: list[Job] = []
    for j in data:
        if not isinstance(j, dict) or "id" not in j:
            continue  # first element is a legal/usage notice
        blob = f"{j.get('position','')} {' '.join(j.get('tags', []))} {j.get('description','')}"
        if not text_matches(blob, tokens):
            continue
        url = j.get("url", "")
        jobs.append(Job(
            source="remoteok",
            title=j.get("position", "") or j.get("title", ""),
            company=j.get("company", ""),
            location=j.get("location", "") or "Remote",
            url=url,
            apply_url=j.get("apply_url", url) or url,
            description=html_to_text(j.get("description", "")),
            remote=True,
            salary=_salary(j),
            posted_at=j.get("date", "") or "",
            raw=j,
        ))
        if len(jobs) >= limit:
            break
    return jobs
