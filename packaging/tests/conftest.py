from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "build"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def build_repo(tmp_path: Path) -> tuple[Path, str]:
    """A git repository holding the fixture build, committed once. Returns (path, commit)."""

    repo = tmp_path / "toronto-election-results"
    shutil.copytree(FIXTURE, repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@invalid", "add", ".")
    git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@invalid",
        "commit",
        "-q",
        "-m",
        "Fixture build",
    )
    return repo, git(repo, "rev-parse", "HEAD")


@pytest.fixture
def build_tables():
    from te_package.tables import read_build

    return read_build(FIXTURE / "data" / "out")
