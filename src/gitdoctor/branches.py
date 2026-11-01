from __future__ import annotations

import time
from pathlib import Path

from .gitutil import default_branch, current_branch, git, git_ok, has_commits
from .models import Finding


def _age(days: int) -> str:
    if days >= 365:
        return f"{days // 365}y {days % 365 // 30}mo old"
    if days >= 60:
        return f"{days // 30}mo old"
    return f"{days}d old"


def check_branches(repo: Path, stale_days: int = 90) -> list[Finding]:
    if not has_commits(repo):
        return []
    base = default_branch(repo)
    cur = current_branch(repo)
    now = time.time()

    merged = set()
    if git_ok(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{base}"):
        merged = set(git(repo, "branch", "--merged", base, "--format=%(refname:short)", check=False).split())

    fmt = "%(refname:short)\t%(committerdate:unix)\t%(upstream:track)"
    out: list[Finding] = []
    for row in git(repo, "for-each-ref", "refs/heads", f"--format={fmt}").splitlines():
        name, ts, track = (row.split("\t") + ["", ""])[:3]
        if name in (base, cur) or not ts:
            continue
        days = int((now - int(ts)) // 86400)
        gone = "gone" in track
        is_merged = name in merged
        if is_merged and (days >= stale_days or gone):
            out.append(Finding(
                "branch", "low", "Merged branch, safe to delete",
                f"{name}  ·  {_age(days)}" + ("  ·  remote deleted" if gone else ""),
                fix=f"git branch -d {name}",
            ))
        elif not is_merged and days >= stale_days:
            ahead = git(repo, "rev-list", "--count", f"{base}..{name}", check=False).strip() or "?"
            out.append(Finding(
                "branch", "medium" if gone else "low", "Stale unmerged branch",
                f"{name}  ·  {_age(days)}  ·  {ahead} commit(s) not in {base}"
                + ("  ·  remote deleted" if gone else ""),
                fix=f"git log {base}..{name}  # review, then merge or git branch -D {name}",
            ))
    return out


def check_state(repo: Path) -> list[Finding]:
    out: list[Finding] = []
    dirty = [l for l in git(repo, "status", "--porcelain", check=False).splitlines() if l]
    if dirty:
        out.append(Finding(
            "state", "low", "Uncommitted changes",
            f"{len(dirty)} file(s) modified or untracked",
            fix="git status",
        ))
    if not has_commits(repo):
        return out
    cur = current_branch(repo)
    if cur == "(detached)":
        return out
    upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False).strip()
    if upstream:
        ahead = git(repo, "rev-list", "--count", "@{u}..HEAD", check=False).strip()
        if ahead and ahead != "0":
            out.append(Finding(
                "state", "low", "Unpushed commits",
                f"{ahead} commit(s) on {cur} not on {upstream}",
                fix="git push",
            ))
    elif git(repo, "remote", check=False).strip():
        out.append(Finding(
            "state", "low", "Branch has no upstream",
            f"{cur} is not tracking a remote branch (work may exist only on this machine)",
            fix=f"git push -u origin {cur}",
        ))
    return out
