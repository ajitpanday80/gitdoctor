from __future__ import annotations

import fnmatch
import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .gitutil import GitError, git, has_commits
from .models import Finding

IGNORE_MARKER = "gitdoctor:ignore"
MAX_FILE_BYTES = 1_000_000
MAX_LINE_LEN = 2000

SKIP_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Cargo.lock", "go.sum", "Pipfile.lock", "composer.lock", "uv.lock",
}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".tgz", ".woff", ".woff2", ".ttf", ".mp4", ".mov", ".svg", ".min.js",
}


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    regex: "re.Pattern[str]"
    severity: str
    fix: str


_ROTATE = "Revoke and rotate it now, then purge it from history (git filter-repo)."

RULES: tuple[Rule, ...] = (
    Rule("aws-access-key", "AWS access key ID",
         re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "high", _ROTATE),
    Rule("github-token", "GitHub token",
         re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b"), "high", _ROTATE),
    Rule("slack-token", "Slack token",
         re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "high", _ROTATE),
    Rule("stripe-live-key", "Stripe live key",
         re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"), "high", _ROTATE),
    Rule("google-api-key", "Google API key",
         re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "high", _ROTATE),
    Rule("private-key", "Private key block",
         re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----"),
         "high", "Remove the key from the repo, treat it as compromised, and replace it."),
)

GENERIC = re.compile(
    r"""(?ix)
    \b[\w.-]*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|token)[\w.-]*
    \s*[:=]\s*(['"])(?P<value>[^'"\s]{8,})\1
    """
)
_PLACEHOLDER = re.compile(
    r"(?i)(example|changeme|change_me|your[_-]|placeholder|dummy|sample|xxxx|\*{4}|<.*>|\$\{.*\}|\{\{.*\}\}|todo|fake)"
)


def entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = {c: s.count(c) for c in set(s)}
    return -sum((n / len(s)) * math.log2(n / len(s)) for n in counts.values())


_PREFIX = re.compile(r"^(?:[a-z]{2,6}_(?:live_|test_)?|github_pat_)")


def redact(secret: str) -> str:
    """Show only a harmless provider prefix (e.g. `ghp_`, `sk_live_`), never key material."""
    m = _PREFIX.match(secret)
    keep = m.group(0) if m else secret[:4]
    return keep + "•" * 6 if len(secret) > len(keep) else "•" * len(secret)


def fingerprint(rule_id: str, secret: str) -> str:
    return hashlib.sha256(f"{rule_id}:{secret}".encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Hit:
    rule: Rule
    secret: str


def scan_line(line: str) -> Iterator[Hit]:
    if len(line) > MAX_LINE_LEN or IGNORE_MARKER in line:
        return
    for rule in RULES:
        m = rule.regex.search(line)
        if m:
            yield Hit(rule, m.group(0))
            return  # one finding per line is enough
    m = GENERIC.search(line)
    if m:
        value = m.group("value")
        if entropy(value) >= 3.2 and not _PLACEHOLDER.search(value):
            yield Hit(
                Rule("generic-secret", "Hardcoded credential", GENERIC, "medium",
                     "Move it to an env var or secret manager; rotate if it was ever real."),
                value,
            )


def _is_text_candidate(path: str, excludes: Iterable[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name in SKIP_NAMES or any(path.endswith(s) for s in SKIP_SUFFIXES):
        return False
    return not any(fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(name, pat) for pat in excludes)


def _finding(hit: Hit, path: str, line: int, commit: Optional[str] = None, extra: str = "") -> Finding:
    return Finding(
        kind="secret",
        severity=hit.rule.severity,
        title=hit.rule.name,
        detail=f"{redact(hit.secret)}{extra}",
        path=path,
        line=line,
        commit=commit,
        rule=hit.rule.id,
        fix=hit.rule.fix,
        fingerprint=fingerprint(hit.rule.id, hit.secret),
    )


def scan_working_tree(repo: Path, excludes: Iterable[str] = ()) -> list[Finding]:
    """Scan every tracked file at its current content (what you'd push today)."""
    if not has_commits(repo):
        return []
    out: list[Finding] = []
    files = git(repo, "ls-files", "-z").split("\0")
    for rel in filter(None, files):
        if not _is_text_candidate(rel, excludes):
            continue
        full = repo / rel
        try:
            if not full.is_file() or full.stat().st_size > MAX_FILE_BYTES:
                continue
            raw = full.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8192]:
            continue
        for lineno, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
            for hit in scan_line(line):
                out.append(_finding(hit, rel, lineno))
    return out


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")


def scan_history(
    repo: Path,
    max_commits: int = 1000,
    excludes: Iterable[str] = (),
    skip: Iterable[str] = (),
) -> list[Finding]:
    """Scan lines ever added in history. `skip` = fingerprints already reported."""
    if not has_commits(repo):
        return []
    skip_set = set(skip)
    try:
        log = git(repo, "log", "--all", "-p", "-U0", "--no-color", "--no-ext-diff",
                  f"--max-count={max_commits}", "--format=@@commit %H")
    except GitError:
        return []
    out: list[Finding] = []
    seen: set[str] = set()
    commit = path = ""
    lineno = 0
    for raw in log.splitlines():
        if raw.startswith("@@commit "):
            commit, path = raw.split(" ", 1)[1], ""
        elif raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else ""
        elif raw.startswith("@@"):
            m = _HUNK.match(raw)
            lineno = int(m.group(1)) if m else 0
        elif raw.startswith("+") and not raw.startswith("+++") and path:
            if _is_text_candidate(path, excludes):
                for hit in scan_line(raw[1:]):
                    fp = fingerprint(hit.rule.id, hit.secret)
                    if fp not in skip_set and fp not in seen:
                        seen.add(fp)
                        f = _finding(hit, path, lineno, commit[:8], extra="  (history only)")
                        f.fix = "Already pushed? Assume it's public: rotate it, then rewrite history."
                        out.append(f)
            lineno += 1
    return out
