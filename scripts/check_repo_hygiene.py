#!/usr/bin/env python3
"""Repository hygiene guard.

Inspects ONLY files tracked by Git via ``git ls-files -z`` and fails with
exit code 1 whenever a tracked path matches a forbidden category (build
artifacts, caches, credentials, local env files).

The script never removes files automatically. It prints, per violation:
  - the offending tracked path
  - the category of the problem
  - a suggested ``git rm --cached <path>`` command

Templates ending with ``.env.example`` are explicitly allowed so that
``.env.example``, ``apps/mobile/.env.example`` etc. remain committable.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class Violation:
    """A single tracked-file hygiene violation."""

    path: str
    category: str

    def render(self) -> str:
        return (
            f"[hygiene] {self.category}: {self.path}\n"
            f"  suggested: git rm --cached {self.path}"
        )


def classify(path: str) -> str | None:
    """Return the category name for a forbidden ``path`` or ``None`` if allowed.

    Categories are mutually exclusive; the first matching rule wins. Rules
    intentionally ignore trailing path separators.
    """

    p = PurePosixPath(path)
    name = p.name
    parts = p.parts

    if name.endswith(".env.example"):
        return None

    for part in parts:
        if part == "node_modules":
            return "node_modules_dependency"
        if part == "__pycache__":
            return "python_bytecode_cache"
        if part == ".next":
            return "next_build_cache"
        if part.startswith(".next-stale-"):
            return "next_stale_cache"

    if name == ".env":
        return "secret_env_file"
    if name in {".env.local", ".env.production", ".env.development"}:
        return "secret_env_file"

    if name.endswith(".tsbuildinfo"):
        return "typescript_build_artifact"

    if name.endswith(".pyc"):
        return "python_bytecode_cache"

    return None


def list_tracked_files() -> list[str]:
    """Return the list of Git-tracked files (``git ls-files -z``)."""

    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(
            "[hygiene] git ls-files failed:\n"
            + proc.stderr.decode("utf-8", errors="replace")
        )
        raise SystemExit(2)

    raw = proc.stdout.decode("utf-8", errors="replace")
    return [item for item in raw.split("\0") if item]


def collect_violations(paths: list[str]) -> list[Violation]:
    violations: list[Violation] = []
    for path in paths:
        category = classify(path)
        if category is not None:
            violations.append(Violation(path=path, category=category))
    violations.sort(key=lambda v: (v.category, v.path))
    return violations


def main() -> int:
    tracked = list_tracked_files()
    violations = collect_violations(tracked)

    if not violations:
        print("[hygiene] OK: no tracked artifacts, caches, or secrets detected.")
        return 0

    print(
        f"[hygiene] FAIL: {len(violations)} tracked file(s) violate the hygiene guard.\n"
        "Remove them with `git rm --cached <file>` and let .gitignore keep them out.\n"
    )
    for v in violations:
        print(v.render())
        print()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
