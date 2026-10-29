"""Repo contract: license, CI, synthetic sample, public-repo safety."""

import re
from pathlib import Path

from conftest import REPO, SAMPLE_CSV, SAMPLE_JSONL

_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "dist", "build"}


def _tracked_text():
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS or part.endswith(".egg-info") for part in path.parts):
            continue
        if path == Path(__file__):
            continue
        if path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        yield path, text


def test_sample_is_labeled_synthetic():
    for path in (SAMPLE_JSONL, SAMPLE_CSV):
        first = path.read_text(encoding="utf-8").splitlines()[0]
        lowered = first.casefold()
        assert "synthetic" in lowered
        assert "example" in lowered
        assert "not a real agent log" in lowered
    example = (REPO / "examples" / "README.md").read_text(encoding="utf-8").casefold()
    assert "synthetic" in example


def test_license_ci_and_readme_contract():
    license_text = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Copyright (c) 2026 zlephir42069" in license_text

    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "actions/checkout@v7" in ci
    assert "actions/setup-python@v7" in ci
    assert '"3.10"' in ci
    assert '"3.13"' in ci
    assert "pytest" in ci

    project = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.10"' in project
    assert 'usage-audit = "usage_audit.cli:main"' in project
    assert "PyYAML" in project

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "https://github.com/zlephir42069" in readme
    assert "https://github.com/zlephir42069/zlegbot-wakegate" in readme
    assert "1850 units" in readme
    assert "synthetic" in readme.casefold()
    assert not re.search(r"\d+\s*%", readme)
    assert "$" not in readme


def test_public_repo_safety():
    forbidden = ("youtube", "discord", "BEGIN PRIVATE KEY", "AKIA", "ghp_", "xoxb-")
    for path, text in _tracked_text():
        lowered = text.casefold()
        for word in forbidden:
            assert word.casefold() not in lowered, f"{word} in {path.relative_to(REPO)}"
