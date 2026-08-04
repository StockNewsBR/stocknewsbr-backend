from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest

from check_repo_hygiene import Violation, classify, collect_violations, main


@pytest.mark.parametrize(
    "path,expected_category",
    [
        ("tsconfig.tsbuildinfo", "typescript_build_artifact"),
        ("apps/web/tsconfig.tsbuildinfo", "typescript_build_artifact"),
        ("apps/web/.next/cache/file", "next_build_cache"),
        ("apps/web/.next/BUILD_ID", "next_build_cache"),
        ("apps/web/.next-stale-123/BUILD_ID", "next_stale_cache"),
        ("apps/web/.next-stale-20260329-103821/cache/.tsbuildinfo", "next_stale_cache"),
        ("node_modules/pkg/file", "node_modules_dependency"),
        ("apps/web/node_modules/next/index.js", "node_modules_dependency"),
        ("app/__pycache__/x.pyc", "python_bytecode_cache"),
        ("any/deep/nested/__pycache__/module.cpython-311.pyc", "python_bytecode_cache"),
        ("module.cpython-311.pyc", "python_bytecode_cache"),
        (".env", "secret_env_file"),
        (".env.local", "secret_env_file"),
        (".env.production", "secret_env_file"),
        (".env.development", "secret_env_file"),
        ("apps/web/.env.local", "secret_env_file"),
    ],
)
def test_blocked_paths(path: str, expected_category: str) -> None:
    assert classify(path) == expected_category


@pytest.mark.parametrize(
    "path",
    [
        ".env.example",
        "apps/mobile/.env.example",
        "apps/web/.env.example",
        ".env.example.local",
        "app/services/access_service.py",
        "app/engine/engine_orchestrator.py",
        "main.py",
        "worker.py",
        "tests/test_repo_hygiene.py",
        "apps/web/app/page.tsx",
        "apps/web/components/Header.tsx",
        "apps/mobile/App.tsx",
        "scripts/check_repo_hygiene.py",
        "docs/mission_28b_audit.md",
        "AGENTS.md",
        ".gitignore",
        "pyproject.toml",
        "ruff.toml",
        ".github/workflows/repo-hygiene.yml",
        ".githooks/pre-commit",
        "scripts/install_git_hooks.sh",
    ],
)
def test_allowed_paths(path: str) -> None:
    assert classify(path) is None


def test_env_example_with_other_pyc_sibling_still_block_pyc() -> None:
    # Sanity: .env.example only whitelists the env template itself,
    # it must not override other categories.
    assert classify(".env.example") is None
    assert classify("keep/.env.example") is None
    assert classify("keep/x.pyc") == "python_bytecode_cache"


def test_collect_violations_sorts_by_category_then_path() -> None:
    paths = [
        "app/x.py",
        "tsconfig.tsbuildinfo",
        ".env",
        "apps/web/tsconfig.tsbuildinfo",
        ".env.local",
        "node_modules/pkg/index.js",
    ]
    violations = collect_violations(paths)

    assert violations == [
        Violation(path="node_modules/pkg/index.js", category="node_modules_dependency"),
        Violation(path=".env", category="secret_env_file"),
        Violation(path=".env.local", category="secret_env_file"),
        Violation(path="apps/web/tsconfig.tsbuildinfo", category="typescript_build_artifact"),
        Violation(path="tsconfig.tsbuildinfo", category="typescript_build_artifact"),
    ]

    # app/x.py must be allowed and not present.
    assert all(v.path != "app/x.py" for v in violations)


def test_violation_render_contains_path_category_and_suggested_command() -> None:
    v = Violation(path="apps/web/tsconfig.tsbuildinfo", category="typescript_build_artifact")
    rendered = v.render()

    assert "apps/web/tsconfig.tsbuildinfo" in rendered
    assert "typescript_build_artifact" in rendered
    assert "git rm --cached apps/web/tsconfig.tsbuildinfo" in rendered


def test_main_returns_zero_when_clean(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "check_repo_hygiene.list_tracked_files",
        lambda: ["app/x.py", "scripts/check_repo_hygiene.py", ".env.example"],
    )
    rc = main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "OK: no tracked artifacts" in out


def test_main_returns_one_when_violations(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "check_repo_hygiene.list_tracked_files",
        lambda: ["app/x.py", "tsconfig.tsbuildinfo", ".env"],
    )
    rc = main()
    out = capsys.readouterr().out

    assert rc == 1
    assert "FAIL: 2 tracked file(s)" in out
    assert "tsconfig.tsbuildinfo" in out
    assert "git rm --cached tsconfig.tsbuildinfo" in out
    assert ".env" in out
    assert "git rm --cached .env" in out


def test_main_raises_when_git_ls_files_fails(monkeypatch) -> None:
    import check_repo_hygiene as mod

    def _boom() -> list[str]:
        raise SystemExit(2)

    monkeypatch.setattr(mod, "list_tracked_files", _boom)
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
