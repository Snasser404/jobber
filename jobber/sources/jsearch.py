"""JSearch (RapidAPI) — aggregates Google for Jobs: LinkedIn, Indeed, Glassdoor,
ZipRecruiter, Talent.com (formerly Workopolis), and company sites. Free tier.

Get a key: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch  -> set RAPIDAPI_KEY.
"""
from __future__ import annotations

from .base import http_get, html_to_text
from ..models import Job
from .. import config

API = "https://jsearch.p.rapidapi.com/search"


def _salary(j: dict) -> str:
    lo, hi = j.get("job_min_salary"), j.get("job_max_salary")
    if lo and hi:
        cur = j.get("job_salary_currency") or "$"
        return f"{cur}{int(lo):,} - {cur}{int(hi):,}"
    return ""


def fetch(cfg: dict) -> list[Job]:
    key = config.env("RAPIDAPI_KEY")
    if not key:
        return []
    search = cfg.get("search", {}) or {}
    keywords = search.get("keywords", []) or []
    location = search.get("location", "") or "Canada"
    limit = int(search.get("max_results_per_source", 25))
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}

    jobs: list[Job] = []
    seen: set[str] = set()
    for kw in keywords[:2]:                     # keep free-tier request count low
        query = f"{kw} in {location}" if location else kw
        try:
            data = http_get(API, params={"query": query, "page": "1", "num_pages": "1"},
                            headers=headers).json().get("data", []) or []
        except Exception:
            continue
        for j in data:
            jid = j.get("job_id") or j.get("job_apply_link")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            city = j.get("job_city") or ""
            country = j.get("job_country") or ""
            loc = ", ".join(x for x in [city, country] if x) or location
            publisher = j.get("job_publisher") or "web"
            jobs.append(Job(
                source=f"jsearch:{publisher}",
                title=j.get("job_title", "") or "",
                company=j.get("employer_name", "") or "",
                location=loc,
                url=j.get("job_apply_link", "") or "",
                apply_url=j.get("job_apply_link", "") or "",
                description=html_to_text(j.get("job_description", "")),
                remote=bool(j.get("job_is_remote")),
                salary=_salary(j),
                posted_at=j.get("job_posted_at_datetime_utc", "") or "",
                employment_type=j.get("job_employment_type", "") or "",
                raw=j,
            ))
            if len(jobs) >= limit:
                return jobs
    return jobs
