"""Score each job against the candidate's resume using Claude."""
from __future__ import annotations

from typing import Callable

from .models import Job, RankedJob
from . import llm

SYSTEM = """You are an expert technical recruiter and honest career coach.
You rate how well ONE specific candidate fits a job. Be realistic — do not inflate scores.

The candidate's resume:
-----
{resume}
-----

Scoring guide:
- 90-100: excellent fit, clearly qualified, should apply now.
- 75-89: strong fit, only minor gaps.
- 60-74: partial fit, worth a look, real gaps.
- below 60: weak fit.
Judge against the candidate's ACTUAL experience and seniority."""

PROMPT = """Score this job for the candidate.

JOB TITLE: {title}
COMPANY: {company}
LOCATION: {location}
DESCRIPTION:
{description}

Reply with ONLY a JSON object:
{{"score": <int 0-100>,
 "summary": "<one sentence on why it does/doesn't fit>",
 "reasons": ["<concrete strength matching this job>", "..."],
 "concerns": ["<gap, mismatch, or seniority issue>", "..."],
 "keywords": ["<skill/term from the posting to emphasize when tailoring>", "..."]}}"""


def _rank_one(job: Job, system: str) -> RankedJob:
    data = llm.complete_json(
        PROMPT.format(
            title=job.title, company=job.company,
            location=job.location, description=job.description[:4000],
        ),
        system=system, role="rank", max_tokens=700, cache_system=True,
    )
    return RankedJob(
        job=job,
        score=int(data.get("score", 0) or 0),
        summary=str(data.get("summary", "")),
        reasons=list(data.get("reasons", []) or []),
        concerns=list(data.get("concerns", []) or []),
        keywords=list(data.get("keywords", []) or []),
    )


def rank_jobs(jobs: list[Job], profile: dict, min_score: int = 0,
              on_progress: Callable[[int, int, RankedJob], None] | None = None
              ) -> list[RankedJob]:
    """Score all jobs, drop those under min_score, return sorted best-first."""
    system = SYSTEM.format(resume=profile.get("resume_text", ""))
    ranked: list[RankedJob] = []
    for i, job in enumerate(jobs):
        try:
            rj = _rank_one(job, system)
        except Exception as e:
            rj = RankedJob(job=job, score=0, summary=f"(could not score: {e})")
        ranked.append(rj)
        if on_progress:
            on_progress(i + 1, len(jobs), rj)
    ranked = [r for r in ranked if r.score >= min_score]
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked
