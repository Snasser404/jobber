"""Core data structures passed between the pipeline stages."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Job:
    """A normalized job listing from any source."""
    source: str                 # "remotive", "adzuna", "greenhouse:shopify", ...
    title: str
    company: str
    location: str
    url: str                    # human-viewable listing page
    description: str            # plain-text job description
    apply_url: str = ""         # direct application URL, if known
    remote: bool = False
    salary: str = ""
    posted_at: str = ""
    employment_type: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Stable short id used to de-duplicate and track applications."""
        key = f"{self.source}|{self.company}|{self.title}|{self.url}".lower()
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    @property
    def best_apply_url(self) -> str:
        return self.apply_url or self.url

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["id"] = self.id
        return d


@dataclass
class RankedJob:
    """A Job plus the AI's fit assessment."""
    job: Job
    score: int                  # 0-100 fit score
    summary: str                # one-line why-it-fits
    reasons: list[str] = field(default_factory=list)     # strengths
    concerns: list[str] = field(default_factory=list)    # gaps / mismatches
    keywords: list[str] = field(default_factory=list)    # terms to emphasize when tailoring

    def to_dict(self) -> dict[str, Any]:
        return {
            "job": self.job.to_dict(),
            "score": self.score,
            "summary": self.summary,
            "reasons": self.reasons,
            "concerns": self.concerns,
            "keywords": self.keywords,
        }


@dataclass
class TailoredApplication:
    """Everything generated for one application, ready for preview + approval."""
    job_id: str
    cover_letter: str = ""
    resume_changes: list[str] = field(default_factory=list)   # human-readable list of edits
    resume_docx_path: str = ""                                # tailored resume file
    cover_letter_path: str = ""                               # saved cover letter file
    tailored_summary: str = ""                                # new resume "About me" text
