"""Derive job-search settings from a resume, so the search follows the resume."""
from __future__ import annotations

from . import llm

SYSTEM = "You help a job seeker target their search based on what their resume emphasizes."

PROMPT = """Read this resume and decide the best job-search settings to find roles this
person should apply to RIGHT NOW, based on the focus the resume emphasizes.

RESUME:
-----
{resume}
-----

Return ONLY a JSON object:
{{
  "focus": "<one sentence: the field/role this resume is targeting>",
  "keywords": ["<5-8 job-search phrases a job board would understand, most relevant first>"],
  "suggested_titles": ["<a few exact job titles to look for>"],
  "location": "<city/region from the resume, or '' if none>",
  "remote_ok": <true or false>,
  "seniority": "<intern|junior|mid|senior|lead>"
}}

Keywords must be real search phrases like "PPC specialist" or "growth marketing",
NOT individual skills. Match the resume's emphasis — if it leans technical, return
technical roles; if it leans marketing, return marketing roles."""


def derive_search_profile(resume_text: str) -> dict:
    data = llm.complete_json(
        PROMPT.format(resume=resume_text[:8000]),
        system=SYSTEM, role="rank", max_tokens=700, temperature=0.2,
    )
    keywords = [str(k).strip() for k in (data.get("keywords") or []) if str(k).strip()]
    return {
        "focus": str(data.get("focus", "")).strip(),
        "keywords": keywords[:8],
        "suggested_titles": [str(t).strip() for t in (data.get("suggested_titles") or []) if t],
        "location": str(data.get("location", "")).strip(),
        "remote_ok": bool(data.get("remote_ok", True)),
        "seniority": str(data.get("seniority", "")).strip(),
    }
