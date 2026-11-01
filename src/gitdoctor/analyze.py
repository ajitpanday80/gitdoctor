from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .branches import check_branches, check_state
from .gitutil import GitError, current_branch, default_branch
from .models import RepoReport
from .secrets import scan_history, scan_working_tree


def analyze_repo(
    repo: Path,
    *,
    stale_days: int = 90,
    history: bool = False,
    history_depth: int = 1000,
    excludes: Iterable[str] = (),
) -> RepoReport:
    report = RepoReport(path=str(repo), name=repo.name)
    try:
        report.branch = current_branch(repo)
        report.default_branch = default_branch(repo)
        excludes = list(excludes)
        secrets = scan_working_tree(repo, excludes)
        report.findings += secrets
        if history:
            known = [f.fingerprint for f in secrets if f.fingerprint]
            report.findings += scan_history(repo, history_depth, excludes, skip=known)
        report.findings += check_branches(repo, stale_days)
        report.findings += check_state(repo)
    except GitError as exc:
        report.error = str(exc)
    return report
