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
from .gitutil import git
from .render import render, want_color
from .sarif import to_sarif


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
    p.add_argument("--format", choices=["text", "json", "sarif"], default="text",
                   help="output format; sarif is for GitHub code scanning (default: text)")
    p.add_argument("--json", action="store_true", help="shorthand for --format json")
    p.add_argument("--staged", action="store_true",
                   help="scan only staged changes (for pre-commit hooks); skips branch and state checks")
    p.add_argument("--prune-merged", action="store_true",
                   help="after the report, delete merged stale branches with `git branch -d` (asks first)")
    p.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation with --prune-merged")
    p.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    p.add_argument("--fail-on", choices=["high", "medium", "low", "never"], default="high",
                   help="exit 1 if any finding is at least this severe (default: high)")
    p.add_argument("-V", "--version", action="version", version=f"gitdoctor {__version__}")
    return p


def _toplevel(path: Path) -> Path | None:
    try:
        return Path(git(path, "rev-parse", "--show-toplevel").strip())
    except Exception:
        return None


def prune_merged(reports, assume_yes: bool) -> int:
    """Delete merged branches via `git branch -d` (git itself refuses unmerged ones)."""
    targets = [(r, f.ref) for r in reports for f in r.findings
               if f.kind == "branch" and f.title.startswith("Merged branch") and f.ref]
    if not targets:
        print("Nothing to prune.")
        return 0
    print(f"\n{len(targets)} merged branch(es) can be deleted:")
    for r, ref in targets:
        print(f"  {r.name}: {ref}")
    if not assume_yes:
        if not sys.stdin.isatty():
            print("Not a terminal; re-run with --yes to confirm.", file=sys.stderr)
            return 2
        if input("Delete them with `git branch -d`? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Aborted; nothing deleted.")
            return 0
    for r, ref in targets:
        try:
            git(r.path, "branch", "-d", ref)
            print(f"  deleted {r.name}/{ref}")
        except Exception as exc:  # git refuses if it isn't actually merged
            print(f"  skipped {r.name}/{ref}: {exc}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = "json" if args.json else args.format
    if args.staged and (args.history or args.prune_merged):
        print("gitdoctor: --staged cannot be combined with --history or --prune-merged", file=sys.stderr)
        return 2
    start = time.perf_counter()
    if args.staged:
        top = _toplevel(Path(args.paths[0]))
        repos = [top] if top else []
    else:
        repos = find_repos([Path(x) for x in args.paths], args.max_depth)
    if not repos:
        print("gitdoctor: no git repositories found under: " + ", ".join(args.paths), file=sys.stderr)
        return 2

    def work(repo: Path):
        return analyze_repo(
            repo, stale_days=args.stale_days, history=args.history,
            history_depth=args.history_depth, excludes=args.exclude, staged=args.staged,
        )

    with ThreadPoolExecutor(max_workers=min(8, len(repos))) as pool:
        reports = list(pool.map(work, repos))
    elapsed = time.perf_counter() - start

    if fmt == "json":
        print(json.dumps({"version": __version__, "repos": [r.to_dict() for r in reports]}, indent=2))
    elif fmt == "sarif":
        print(json.dumps(to_sarif(reports), indent=2))
    else:
        print(render(reports, elapsed, want_color(args.color), args.history, staged=args.staged))
        if args.prune_merged:
            rc = prune_merged(reports, args.yes)
            if rc:
                return rc

    if args.fail_on == "never":
        return 0
    bar = SEVERITY_ORDER[args.fail_on]
    return int(any(SEVERITY_ORDER[f.severity] >= bar for r in reports for f in r.findings))
