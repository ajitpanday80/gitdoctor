from __future__ import annotations

import os
import subprocess
from pathlib import Path

ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.com",
}

# Tokens are assembled at runtime so no real-looking secret is stored in this repo.
def aws_key() -> str:
    return "AK" + "IA" + "QWERTY7890ABCDEF"

def github_token() -> str:
    return "gh" + "p_" + "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5"


def sh(repo: Path, *args: str, date: str | None = None) -> str:
    env = dict(ENV)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True, env=ENV)
    return path


def commit(repo: Path, files: dict[str, str], msg: str = "c", date: str | None = None) -> None:
    for name, content in files.items():
        f = repo / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", msg, date=date)
