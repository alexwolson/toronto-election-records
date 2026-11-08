"""Fetch one pinned build of toronto-election-results and check it against its manifest.

A package is made from one commit of the build repository. The pin names the commit and, for a
release, the tag that must point at it. The commit is fetched with git, archived as `git archive`
writes it (that archive goes into the provenance supplement) and extracted for reading. Every file
in `data/out/` must match the SHA-256 the build's manifest records, and the manifest must list
every file there.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path


class InputError(Exception):
    """The pinned build cannot be fetched or does not match its manifest."""


@dataclass(frozen=True)
class BuildPin:
    repository: str
    commit: str
    tag: str | None = None

    @property
    def is_release(self) -> bool:
        return self.tag is not None

    @property
    def version(self) -> str:
        return self.tag if self.tag else f"dev-{self.commit[:7]}"


@dataclass(frozen=True)
class FetchedBuild:
    root: Path
    archive: Path


def load_pin(path: Path) -> BuildPin:
    build = tomllib.loads(path.read_text(encoding="utf-8"))["build"]
    return BuildPin(build["repository"], build["commit"], build.get("tag") or None)


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise InputError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _url(repository: str) -> str:
    path = Path(repository)
    return path.resolve().as_uri() if path.exists() else repository


def _check_tag(pin: BuildPin) -> None:
    refs = _git(
        "ls-remote", _url(pin.repository), f"refs/tags/{pin.tag}", f"refs/tags/{pin.tag}^{{}}"
    )
    found = {line.split("\t")[1]: line.split("\t")[0] for line in refs.splitlines()}
    commit = found.get(f"refs/tags/{pin.tag}^{{}}", found.get(f"refs/tags/{pin.tag}"))
    if commit is None:
        raise InputError(f"the tag {pin.tag} does not exist in {pin.repository}")
    if commit != pin.commit:
        raise InputError(
            f"the tag {pin.tag} points at {commit}, not the pinned commit {pin.commit}"
        )


def fetch_build(pin: BuildPin, cache: Path) -> FetchedBuild:
    """Fetch the pinned commit into `cache`, archive it and extract the archive."""

    if pin.is_release:
        _check_tag(pin)
    repo = cache / "repository.git"
    if not repo.exists():
        repo.mkdir(parents=True)
        _git("init", "-q", "--bare", cwd=repo)
    _git("fetch", "-q", "--depth", "1", _url(pin.repository), pin.commit, cwd=repo)
    name = f"toronto-election-results-{pin.version}"
    archive = cache / f"{name}.zip"
    _git(
        "archive",
        "--format=zip",
        f"--prefix={name}/",
        "-o",
        str(archive.resolve()),
        pin.commit,
        cwd=repo,
    )
    # Extract into a fresh folder named for this commit inside the cache; nothing else is removed.
    root = cache / f"extracted-{pin.commit}"
    if root.exists():
        shutil.rmtree(root)
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(root)
    return FetchedBuild(root=root / name, archive=archive)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_outputs(root: Path) -> dict:
    """Check every file in data/out/ against the build manifest and return the manifest."""

    out = root / "data" / "out"
    manifest = json.loads((out / "build_manifest.json").read_text(encoding="utf-8"))
    listed = {}
    for record in manifest["artifacts"]:
        listed[record["local_path"]] = record["sha256"]
    present = {
        f"data/out/{p.name}"
        for p in out.iterdir()
        if p.is_file() and p.name != "build_manifest.json"
    }
    problems = [f"{path} is not in the build manifest" for path in sorted(present - set(listed))]
    problems += [
        f"{path} is in the build manifest but missing" for path in sorted(set(listed) - present)
    ]
    for path in sorted(present & set(listed)):
        if sha256(root / path) != listed[path]:
            problems.append(f"{path} does not match the SHA-256 in the build manifest")
    if problems:
        raise InputError("; ".join(problems))
    return manifest
