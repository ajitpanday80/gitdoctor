from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3}


@dataclass
class Finding:
    kind: str  # "secret" | "branch" | "state"
    severity: str  # "low" | "medium" | "high"
    title: str
    detail: str = ""
    path: Optional[str] = None
    line: Optional[int] = None
    commit: Optional[str] = None
    rule: Optional[str] = None
    fix: Optional[str] = None
    fingerprint: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class RepoReport:
    path: str
    name: str
    branch: str = ""
    default_branch: str = ""
    findings: list[Finding] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def score(self) -> int:
        """Heuristic 0-100 health score. Not a security guarantee."""
        penalty = {"secret-high": 0, "secret-medium": 0, "branch": 0, "state": 0}
        for f in self.findings:
            if f.kind == "secret":
                key = "secret-high" if f.severity == "high" else "secret-medium"
                penalty[key] += 20 if f.severity == "high" else 8
            elif f.kind == "branch":
                penalty["branch"] += 1 if "merged" in f.title else 2
            else:
                penalty["state"] += 5
        total = (
            min(penalty["secret-high"], 60)
            + min(penalty["secret-medium"], 24)
            + min(penalty["branch"], 10)
            + min(penalty["state"], 10)
        )
        score = max(0, 100 - total)
        if any(f.kind == "secret" and f.severity == "high" for f in self.findings):
            score = min(score, 55)  # a leaked credential can never be a "good" repo
        return score

    @property
    def grade(self) -> str:
        s = self.score
        for cutoff, letter in ((90, "A"), (75, "B"), (60, "C"), (40, "D")):
            if s >= cutoff:
                return letter
        return "F"

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "branch": self.branch,
            "default_branch": self.default_branch,
            "score": self.score,
            "grade": self.grade,
            "error": self.error,
            "findings": [f.to_dict() for f in self.findings],
        }
