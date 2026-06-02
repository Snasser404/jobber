"""Job-source registry: fetch from every enabled source and merge results."""
from __future__ import annotations

from typing import Callable

from ..models import Job
from . import remotive, remoteok, arbeitnow, adzuna, greenhouse, lever, jsearch

# name -> fetch(cfg) -> list[Job]
SOURCES: dict[str, Callable[[dict], list[Job]]] = {
    "jsearch": jsearch.fetch,      # LinkedIn/Indeed/Glassdoor/Talent.com via Google for Jobs
    "adzuna": adzuna.fetch,
    "remotive": remotive.fetch,
    "remoteok": remoteok.fetch,
    "arbeitnow": arbeitnow.fetch,
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
}


def _apply_filters(jobs: list[Job], cfg: dict) -> list[Job]:
    filt = cfg.get("filters", {}) or {}
    excl_kw = [k.lower() for k in filt.get("exclude_keywords", []) or []]
    excl_co = [c.lower() for c in filt.get("exclude_companies", []) or []]
    out: list[Job] = []
    for j in jobs:
        title = (j.title or "").lower()
        company = (j.company or "").lower()
        if any(k in title for k in excl_kw):
            continue
        if any(c in company for c in excl_co):
            continue
        if not j.title or not j.url:
            continue
        out.append(j)
    return out


def fetch_all(cfg: dict, on_progress: Callable[[str, int], None] | None = None
              ) -> tuple[list[Job], dict[str, int]]:
    """Run all sources, de-duplicate, filter. Returns (jobs, per-source counts)."""
    all_jobs: list[Job] = []
    stats: dict[str, int] = {}
    for name, fn in SOURCES.items():
        try:
            res = fn(cfg)
        except Exception:
            res = []
        stats[name] = len(res)
        all_jobs.extend(res)
        if on_progress:
            on_progress(name, len(res))

    unique: dict[str, Job] = {}
    for j in all_jobs:
        unique.setdefault(j.id, j)

    return _apply_filters(list(unique.values()), cfg), stats
