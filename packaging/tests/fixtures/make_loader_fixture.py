"""Build the package the loaders' tests read, and a registry that lists it.

The R, Python and Stata loaders are tested against one real package made by `te-package` from
the sample build in `tests/fixtures/build`, with no network. This script commits the sample
build to a temporary git repository with a fixed author and date (so the commit, and the
version name `dev-<commit>`, stay the same), builds the package, and writes to `fixtures/` at
the repository root:

- the package ZIP;
- `versions.csv`, a registry in the published format whose `package_url` is the ZIP's file name,
  which the loaders resolve next to the registry.

Usage:
    uv run python tests/fixtures/make_loader_fixture.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from te_package.assemble import build_package
from te_package.build_input import BuildPin, sha256
from te_package.checks import posix_cksum
from te_package.codebook import REPO_ROOT, load_codebook

SAMPLE = Path(__file__).parent / "build"
OUT = REPO_ROOT / "fixtures"
REGISTRY_COLUMNS = [
    "version",
    "published",
    "doi",
    "record_url",
    "build_commit",
    "schema_version",
    "package_url",
    "package_bytes",
    "package_sha256",
    "package_cksum",
]


def _git(repo: Path, *args: str) -> str:
    env = os.environ | {
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@invalid",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@invalid",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
    }
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "toronto-election-results"
        shutil.copytree(SAMPLE, repo)
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "Sample build")
        commit = _git(repo, "rev-parse", "HEAD")
        built = build_package(BuildPin(str(repo), commit), Path(tmp) / "cache", Path(tmp) / "dist")
        OUT.mkdir(exist_ok=True)
        for old in OUT.glob("toronto-election-records-*.zip"):
            old.unlink()
        target = OUT / built.package_zip.name
        shutil.copy2(built.package_zip, target)
    crc, length = posix_cksum(target)
    registry = pd.DataFrame(
        [
            {
                "version": built.version,
                "published": "2026-01-01",
                "doi": "",
                "record_url": "",
                "build_commit": commit,
                "schema_version": load_codebook().schema_version,
                "package_url": target.name,
                "package_bytes": length,
                "package_sha256": sha256(target),
                "package_cksum": crc,
            }
        ],
        columns=REGISTRY_COLUMNS,
    )
    registry.to_csv(OUT / "versions.csv", index=False)
    print(f"wrote {target.relative_to(REPO_ROOT)} ({length:,} bytes) and fixtures/versions.csv")


if __name__ == "__main__":
    main()
