from __future__ import annotations

import os
from pathlib import Path

SKIP_DIRS = {
    "node_modules", ".venv", "venv", "__pycache__", ".cache", ".npm",
    ".cargo", "target", "dist", "build", ".tox", "Library", ".Trash",
}


def find_repos(roots: list[Path], max_depth: int = 4) -> list[Path]:
    """Find git working trees under `roots`. Does not descend into found repos."""
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        root = root.expanduser().resolve()
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            here = Path(dirpath)
            if ".git" in dirnames or ".git" in filenames:
                if here not in seen:
                    seen.add(here)
                    found.append(here)
                dirnames[:] = []
                continue
            if len(here.parts) - base_depth >= max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
    return found
