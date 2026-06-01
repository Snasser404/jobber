"""Arbeitnow — free job-board API, no key required."""
from __future__ import annotations

from .base import http_get, html_to_text, keyword_tokens, text_matches, looks_remote
from ..models import Job

API = "https://www.arbeitnow.com/api/job-board-api"


def fetch(cfg: dict) -> list[Job]:
    search = cfg.get("search", {}) or {}
    limit = int(search.get("max_results_per_source", 25))
    tokens = keyword_tokens(search.get("keywords", []))
    jobs: list[Job] = []
    seen: set[str] = set()
    # Pull a couple of pages, then filter locally by keyword.
    for page in (1, 2):
        try:
            data = http_get(API, params={"page": page}).json().get("data", [])
        except Exception:
            break
        if not data:
            break
        for j in data:
            blob = f"{j.get('title','')} {j.get('description','')} {' '.join(j.get('tags', []))}"
            if not text_matches(blob, tokens):
                continue
            url = j.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            jobs.append(Job(
                source="arbeitnow",
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                location=j.get("location", "") or "",
                url=url,
                apply_url=url,
                description=html_to_text(j.get("description", "")),
                remote=bool(j.get("remote")) or looks_remote(j.get("title", "")),
                posted_at=str(j.get("created_at", "")),
                employment_type=", ".join(j.get("job_types", []) or []),
                raw=j,
            ))
            if len(jobs) >= limit:
                return jobs
    return jobs
