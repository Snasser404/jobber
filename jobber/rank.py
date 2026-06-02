"""Score jobs against the candidate's resume. Batches many jobs per LLM call to
keep cost + request-count low (important for cheap/free providers)."""
from __future__ import annotations

from typing import Callable

from .models import Job, RankedJob
from . import llm

SYSTEM = """You are an expert technical recruiter and honest career coach.
You rate how well ONE specific candidate fits each job. Be realistic — do not inflate scores.

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

BATCH_PROMPT = """Score EACH job below for the candidate.

Reply with ONLY a JSON array — exactly one object per job, keyed by its index "i":
[{{"i": <index>, "score": <int 0-100>, "summary": "<one sentence on fit>",
  "reasons": ["<concrete strength>"], "concerns": ["<gap or mismatch>"],
  "keywords": ["<term from the posting to emphasize when tailoring>"]}}]

JOBS:
{jobs}"""

ONE_PROMPT = """Score this job for the candidate.

JOB TITLE: {title}
COMPANY: {company}
LOCATION: {location}
DESCRIPTION:
{description}

Reply with ONLY a JSON object:
{{"score": <int 0-100>, "summary": "<one sentence>",
 "reasons": ["<strength>"], "concerns": ["<gap>"], "keywords": ["<term to emphasize>"]}}"""


def _to_ranked(job: Job, r: dict) -> RankedJob:
    return RankedJob(
        job=job,
        score=int(r.get("score", 0) or 0),
        summary=str(r.get("summary", "")),
        reasons=list(r.get("reasons", []) or []),
        concerns=list(r.get("concerns", []) or []),
        keywords=list(r.get("keywords", []) or []),
    )


def _fmt_jobs(batch: list[Job]) -> str:
    parts = []
    for idx, job in enumerate(batch):
        desc = (job.description or "")[:700]
        parts.append(f"[{idx}] TITLE: {job.title} | COMPANY: {job.company} | "
                     f"LOCATION: {job.location}\nDESCRIPTION: {desc}")
    return "\n---\n".join(parts)


def _rank_batch(batch: list[Job], system: str) -> list[RankedJob | None]:
    data = llm.complete_json(BATCH_PROMPT.format(jobs=_fmt_jobs(batch)),
                             system=system, role="rank", max_tokens=2200, cache_system=True)
    by_i: dict[int, dict] = {}
    if isinstance(data, list):
        for r in data:
            try:
                by_i[int(r.get("i"))] = r
            except Exception:
                continue
    return [(_to_ranked(job, by_i[idx]) if idx in by_i else None)
            for idx, job in enumerate(batch)]


def _rank_one(job: Job, system: str) -> RankedJob:
    data = llm.complete_json(
        ONE_PROMPT.format(title=job.title, company=job.company,
                          location=job.location, description=job.description[:4000]),
        system=system, role="rank", max_tokens=700, cache_system=True)
    return _to_ranked(job, data if isinstance(data, dict) else {})


def rank_jobs(jobs: list[Job], profile: dict, min_score: int = 0,
              on_progress: Callable[[int, int, RankedJob], None] | None = None,
              batch_size: int = 6) -> list[RankedJob]:
    """Score all jobs (batched), drop those under min_score, return sorted best-first."""
    system = SYSTEM.format(resume=profile.get("resume_text", ""))
    ranked: list[RankedJob] = []
    done = 0
    for start in range(0, len(jobs), batch_size):
        batch = jobs[start:start + batch_size]
        try:
            results = _rank_batch(batch, system)
        except Exception:
            results = [None] * len(batch)
        for job, rj in zip(batch, results):
            if rj is None:                       # batch missed this one → try single, else 0
                try:
                    rj = _rank_one(job, system)
                except Exception:
                    rj = RankedJob(job=job, score=0, summary="(could not score)")
            ranked.append(rj)
            done += 1
            if on_progress:
                on_progress(done, len(jobs), rj)
    ranked = [r for r in ranked if r.score >= min_score]
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked
