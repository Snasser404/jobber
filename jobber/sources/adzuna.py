"""Adzuna — large aggregator with good Canadian coverage. Free API key required."""
from __future__ import annotations

from .base import http_get, html_to_text, looks_remote
from ..models import Job
from .. import config


def _salary(j: dict) -> str:
    lo, hi = j.get("salary_min"), j.get("salary_max")
    if lo and hi:
        return f"${int(lo):,} - ${int(hi):,}"
    return ""


def fetch(cfg: dict) -> list[Job]:
    if not config.has_adzuna_keys():
        return []
    search = cfg.get("search", {}) or {}
    country = search.get("country", "ca")
    location = search.get("location", "")
    keywords = search.get("keywords", []) or []
    limit = int(search.get("max_results_per_source", 25))
    app_id = config.env("ADZUNA_APP_ID")
    app_key = config.env("ADZUNA_APP_KEY")
    jobs: list[Job] = []
    seen: set[str] = set()
    for kw in keywords[:4]:
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        params = {
            "app_id": app_id, "app_key": app_key,
            "what": kw, "where": location,
            "results_per_page": min(limit, 50),
            "content-type": "application/json",
        }
        try:
            data = http_get(url, params=params).json().get("results", [])
        except Exception:
            continue
        for j in data:
            jid = str(j.get("id", ""))
            if jid in seen:
                continue
            seen.add(jid)
            desc = j.get("description", "")
            jobs.append(Job(
                source="adzuna",
                title=j.get("title", ""),
                company=(j.get("company") or {}).get("display_name", ""),
                location=(j.get("location") or {}).get("display_name", ""),
                url=j.get("redirect_url", ""),
                apply_url=j.get("redirect_url", ""),
                description=html_to_text(desc),
                remote=looks_remote(j.get("title", ""), desc),
                salary=_salary(j),
                posted_at=j.get("created", "") or "",
                employment_type=j.get("contract_time", "") or "",
                raw=j,
            ))
    return jobs
