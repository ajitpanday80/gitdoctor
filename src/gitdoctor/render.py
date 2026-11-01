from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .models import Finding, RepoReport


class Style:
    def __init__(self, color: bool):
        self.color = color

    def _w(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.color else s

    def bold(self, s): return self._w("1", s)
    def dim(self, s): return self._w("2", s)
    def red(self, s): return self._w("38;5;203", s)
    def yellow(self, s): return self._w("38;5;221", s)
    def green(self, s): return self._w("38;5;114", s)
    def blue(self, s): return self._w("38;5;111", s)
    def violet(self, s): return self._w("38;5;183", s)
    def gray(self, s): return self._w("38;5;245", s)


def want_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never" or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _home(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home) else path


def _grade_color(st: Style, grade: str):
    return {"A": st.green, "B": st.green, "C": st.yellow, "D": st.yellow}.get(grade, st.red)


def _bar(st: Style, score: int, grade: str, width: int = 10) -> str:
    filled = round(score / 100 * width)
    return _grade_color(st, grade)("█" * filled) + st.gray("░" * (width - filled))


_SEV = {"high": ("HIGH", "red"), "medium": ("MED ", "yellow"), "low": ("LOW ", "blue")}


def _sev_tag(st: Style, sev: str) -> str:
    label, color = _SEV[sev]
    return getattr(st, color)(st.bold(label))


def _group(findings: list[Finding], kind: str) -> list[Finding]:
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted((f for f in findings if f.kind == kind), key=lambda f: (order[f.severity], f.path or "", f.line or 0))


def render(reports: list[RepoReport], elapsed: float, color: bool, history: bool) -> str:
    st = Style(color)
    width = min(shutil.get_terminal_size((100, 24)).columns, 100)
    out: list[str] = []
    p = out.append

    total_f = sum(len(r.findings) for r in reports)
    p("")
    p(f" {st.bold(st.violet('gitdoctor'))} {st.gray('v' + __version__)}  "
      f"{st.gray('·')}  scanned {st.bold(str(len(reports)))} repo{'s' if len(reports) != 1 else ''} "
      f"in {elapsed:.2f}s{st.gray('  ·  history scan on') if history else ''}")
    p("")

    for r in sorted(reports, key=lambda r: (r.score, r.name)):
        gc = _grade_color(st, r.grade)
        head = f" {st.bold(_home(r.path))}  {st.gray(r.branch)}"
        score = f"{_bar(st, r.score, r.grade)} {gc(st.bold(str(r.score)))}{st.gray('/100')} {gc(st.bold(r.grade))}"
        p(head)
        p(f" {score}")
        if r.error:
            p(f"   {st.red('error:')} {r.error}")
            p("")
            continue
        if not r.findings:
            p(f"   {st.green('✔')} {st.dim('clean: no secrets, no stale branches, nothing unpushed')}")
            p("")
            continue

        secrets = _group(r.findings, "secret")
        if secrets:
            p(f"   {st.red(st.bold('✖ Secrets'))} {st.gray(f'({len(secrets)})')}")
            for f in secrets:
                loc = f"{f.path}:{f.line}"
                if f.commit:
                    loc += f" @{f.commit}"
                p(f"     {_sev_tag(st, f.severity)} {f.title}  {st.gray(loc)}")
                p(f"          {st.yellow(f.detail)}")
                if f.fix:
                    p(f"          {st.gray('→ ' + f.fix)}")
        branches = _group(r.findings, "branch")
        if branches:
            p(f"   {st.yellow(st.bold('⚠ Branches'))} {st.gray(f'({len(branches)})')}")
            for f in branches:
                p(f"     {_sev_tag(st, f.severity)} {f.title}")
                p(f"          {f.detail}")
                if f.fix:
                    p(f"          {st.gray('$ ' + f.fix)}")
        state = _group(r.findings, "state")
        if state:
            p(f"   {st.blue(st.bold('● Working state'))} {st.gray(f'({len(state)})')}")
            for f in state:
                p(f"     {_sev_tag(st, f.severity)} {f.title}: {f.detail}")
        p("")

    highs = sum(1 for r in reports for f in r.findings if f.severity == "high")
    secrets_n = sum(1 for r in reports for f in r.findings if f.kind == "secret")
    branches_n = sum(1 for r in reports for f in r.findings if f.kind == "branch")
    line = st.gray("─" * (width - 2))
    p(f" {line}")
    summary = (
        f" {st.bold(str(total_f))} finding{'s' if total_f != 1 else ''}  "
        f"{st.gray('·')}  {st.red(str(secrets_n))} secrets  "
        f"{st.gray('·')}  {st.yellow(str(branches_n))} branches"
    )
    p(summary)
    if highs:
        p(f" {st.red('✖')} {highs} high-severity finding{'s' if highs != 1 else ''}: exit code 1")
    elif total_f == 0:
        p(f" {st.green('✔')} all clear")
    p("")
    return "\n".join(out)
