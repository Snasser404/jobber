"""Lever — pull jobs straight from a company's careers board. No key."""
from __future__ import annotations

from .base import http_get, html_to_text, keyword_tokens, text_matches, looks_remote
from ..models import Job


def fetch(cfg: dict) -> list[Job]:
    companies = ((cfg.get("ats", {}) or {}).get("lever", []) or [])
    kw_tokens = keyword_tokens((cfg.get("search", {}) or {}).get("keywords", []))
    jobs: list[Job] = []
    for company in companies:
        url = f"https://api.lever.co/v0/postings/{company}"
        try:
            data = http_get(url, params={"mode": "json"}).json()
        except Exception:
            continue
        for j in data:
            cats = j.get("categories", {}) or {}
            desc = j.get("descriptionPlain") or j.get("description", "")
            blob = f"{j.get('text','')} {desc}"
            if not text_matches(blob, kw_tokens):
                continue
            loc = cats.get("location", "")
            jobs.append(Job(
                source=f"lever:{company}",
                title=j.get("text", ""),
                company=company.replace("-", " ").title(),
                location=loc,
                url=j.get("hostedUrl", ""),
                apply_url=j.get("applyUrl", j.get("hostedUrl", "")),
                description=html_to_text(desc),
                remote=looks_remote(loc, cats.get("commitment", "")),
                employment_type=cats.get("commitment", "") or "",
                posted_at=str(j.get("createdAt", "")),
                raw=j,
            ))
    return jobs
