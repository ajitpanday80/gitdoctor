from __future__ import annotations

from . import __version__
from .models import RepoReport

_LEVEL = {"high": "error", "medium": "warning", "low": "note"}


def to_sarif(reports: list[RepoReport]) -> dict:
    """SARIF 2.1.0 for GitHub code scanning. Only secret findings (they have file locations)."""
    multi = len(reports) > 1
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for r in reports:
        for f in r.findings:
            if f.kind != "secret" or not f.path:
                continue
            rid = f.rule or "secret"
            rules.setdefault(rid, {
                "id": rid,
                "name": f.title,
                "shortDescription": {"text": f.title},
                "help": {"text": f.fix or "Rotate the credential and remove it from the repository."},
            })
            uri = f"{r.name}/{f.path}" if multi else f.path
            results.append({
                "ruleId": rid,
                "level": _LEVEL[f.severity],
                "message": {"text": f"{f.title} ({f.detail.strip()})"},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": f.line or 1},
                }}],
                "partialFingerprints": {"gitdoctor/v1": f.fingerprint or ""},
            })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "gitdoctor",
                "version": __version__,
                "informationUri": "https://github.com/ajitpanday80/something",
                "rules": list(rules.values()),
            }},
            "results": results,
        }],
    }
