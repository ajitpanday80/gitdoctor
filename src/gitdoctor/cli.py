from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import __version__
from .analyze import analyze_repo
from .discover import find_repos
from .models import SEVERITY_ORDER
from .render import render, want_color


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gitdoctor",
        description="Health check for every git repo on your machine: leaked secrets, "
                    "stale branches, unpushed work. Read-only; never modifies a repo.",
    )
    p.add_argument("paths", nargs="*", default=["."], help="directories to search for repos (default: .)")
    p.add_argument("--history", action="store_true", help="also scan secrets ever committed (slower)")
    p.add_argument("--history-depth", type=int, default=1000, metavar="N",
                   help="max commits to scan with --history (default: 1000)")
    p.add_argument("--stale-days", type=int, default=90, metavar="N",
                   help="days before a branch counts as stale (default: 90)")
    p.add_argument("--max-depth", type=int, default=4, metavar="N", help="how deep to look for repos (default: 4)")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="skip files matching GLOB (repeatable)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    p.add_argument("--fail-on", choices=["high", "medium", "low", "never"], default="high",
                   help="exit 1 if any finding is at least this severe (default: high)")
    p.add_argument("-V", "--version", action="version", version=f"gitdoctor {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    start = time.perf_counter()
    repos = find_repos([Path(x) for x in args.paths], args.max_depth)
    if not repos:
        print("gitdoctor: no git repositories found under: " + ", ".join(args.paths), file=sys.stderr)
        return 2

    def work(repo: Path):
        return analyze_repo(
            repo, stale_days=args.stale_days, history=args.history,
            history_depth=args.history_depth, excludes=args.exclude,
        )

    with ThreadPoolExecutor(max_workers=min(8, len(repos))) as pool:
        reports = list(pool.map(work, repos))
    elapsed = time.perf_counter() - start

    if args.json:
        print(json.dumps({"version": __version__, "repos": [r.to_dict() for r in reports]}, indent=2))
    else:
        print(render(reports, elapsed, want_color(args.color), args.history))

    if args.fail_on == "never":
        return 0
    bar = SEVERITY_ORDER[args.fail_on]
    return int(any(SEVERITY_ORDER[f.severity] >= bar for r in reports for f in r.findings))
