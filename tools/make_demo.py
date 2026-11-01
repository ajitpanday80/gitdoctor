#!/usr/bin/env python3
"""Build a throwaway workspace of realistic, messy repos for demos and screenshots.

    python tools/make_demo.py /tmp/demo-home/code

All "secrets" are fake and assembled at runtime, so nothing token-shaped is stored in this repo.
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ENV = {**os.environ, "GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@example.com",
       "GIT_COMMITTER_NAME": "Dev", "GIT_COMMITTER_EMAIL": "dev@example.com"}


def git(repo, *a, date=None):
    env = dict(ENV)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, env=env)


def init(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True, env=ENV)
    return path


def commit(repo, files, msg, date):
    for n, c in files.items():
        f = repo / n
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(c)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg, date=date)


def ago(days: int) -> str:
    """ISO date `days` before now, so the demo never goes stale."""
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


def main(root: Path):
    aws = "AK" + "IA" + "7XQ2MZPL4TWB9KDC"
    gh = "gh" + "p_" + "Zk3Lm9Qw2Xv7Rt5Yb1Nc8Hd4Fj6Gs0Ap3UeK7"
    stripe = "sk_" + "live_" + "51Hq8dKzX4mNvB2tRw7YcLp9"

    # 1. payments-api: the repo that makes you sweat
    r = init(root / "payments-api")
    commit(r, {"app/main.py": "print('ok')\n", "config/prod.env": f"AWS_ACCESS_KEY_ID={aws}\nDB_HOST=db.internal\n"},
           "initial service", ago(430))
    commit(r, {"app/billing.py": f'STRIPE_KEY = "{stripe}"\n'}, "add billing", ago(390))
    git(r, "checkout", "-q", "-b", "feature/refunds")
    commit(r, {"app/refunds.py": "# wip\n"}, "refunds wip", ago(160))
    git(r, "checkout", "-q", "main")
    git(r, "checkout", "-q", "-b", "hotfix/rounding")
    commit(r, {"app/round.py": "x = 1\n"}, "fix rounding", ago(210))
    git(r, "checkout", "-q", "main")
    git(r, "merge", "-q", "--no-ff", "hotfix/rounding", "-m", "merge hotfix", date=ago(209))
    git(r, "branch", "experiment/grpc")
    git(r, "checkout", "-q", "experiment/grpc")
    commit(r, {"app/grpc.py": "# try\n"}, "grpc spike", ago(300))
    git(r, "checkout", "-q", "main")
    (r / "notes.txt").write_text("todo\n")

    # 2. ml-experiments: secret was "removed" but still lives in history
    r = init(root / "ml-experiments")
    commit(r, {"train.py": "import torch\n", ".env": f"GITHUB_TOKEN={gh}\n"}, "first run", ago(120))
    commit(r, {".env": "GITHUB_TOKEN=\n"}, "oops, remove token", ago(119))
    git(r, "checkout", "-q", "-b", "try-lora")
    commit(r, {"lora.py": "# a\n"}, "lora", ago(140))
    git(r, "checkout", "-q", "main")

    # 3 + 4. healthy repos
    for name in ("personal-site", "dotfiles"):
        r = init(root / name)
        commit(r, {"README.md": f"# {name}\n"}, "init", ago(12))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
