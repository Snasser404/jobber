"""Remotive — free remote-jobs API, no key required."""
from __future__ import annotations

from .base import http_get, html_to_text
from ..models import Job

API = "https://remotive.com/api/remote-jobs"


def fetch(cfg: dict) -> list[Job]:
    search = cfg.get("search", {}) or {}
    if not search.get("remote_ok", True):
        return []
    keywords = search.get("keywords", []) or []
    limit = int(search.get("max_results_per_source", 25))
    jobs: list[Job] = []
    seen: set[str] = set()
    for kw in keywords[:5]:
        try:
            data = http_get(API, params={"search": kw, "limit": limit}).json().get("jobs", [])
        except Exception:
            continue
        for j in data:
            url = j.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            jobs.append(Job(
                source="remotive",
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                location=j.get("candidate_required_location", "Remote") or "Remote",
                url=url,
                apply_url=url,
                description=html_to_text(j.get("description", "")),
                remote=True,
                salary=j.get("salary", "") or "",
                posted_at=j.get("publication_date", "") or "",
                employment_type=j.get("job_type", "") or "",
                raw=j,
            ))
    return jobs
