from __future__ import annotations

import os
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}


def git(repo: Path | str, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        errors="replace",
        env=_ENV,
    )
    if check and proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def git_ok(repo: Path | str, *args: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            env=_ENV,
        ).returncode
        == 0
    )


def current_branch(repo: Path) -> str:
    out = git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False).strip()
    return out or "(detached)"


def default_branch(repo: Path) -> str:
    ref = git(repo, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD", check=False).strip()
    if ref:
        return ref.split("/", 1)[1]
    for name in ("main", "master", "trunk", "develop"):
        if git_ok(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{name}"):
            return name
    return current_branch(repo)


def has_commits(repo: Path) -> bool:
    return git_ok(repo, "rev-parse", "--verify", "--quiet", "HEAD")
