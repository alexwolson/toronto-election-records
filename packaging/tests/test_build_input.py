from __future__ import annotations

import json
import zipfile

import pytest
from conftest import git

from te_package.build_input import BuildPin, InputError, fetch_build, load_pin, verify_outputs


def test_version_is_the_tag_or_a_dev_name():
    sha = "e090bf76d992f96550ad19b99b53011a0911b791"
    assert BuildPin("repo", sha, "results-2026-11-30.1").version == "results-2026-11-30.1"
    assert BuildPin("repo", sha).version == "dev-e090bf7"
    assert not BuildPin("repo", sha).is_release


def test_load_pin_reads_build_toml(tmp_path):
    path = tmp_path / "build.toml"
    path.write_text(
        '[build]\nrepository = "https://example.invalid/r"\ncommit = "abc1234def"\ntag = ""\n',
        encoding="utf-8",
    )
    pin = load_pin(path)
    assert pin == BuildPin("https://example.invalid/r", "abc1234def", None)


def test_fetch_build_extracts_the_commit_and_keeps_its_archive(build_repo, tmp_path):
    repo, sha = build_repo
    fetched = fetch_build(BuildPin(str(repo), sha), tmp_path / "cache")
    assert (fetched.root / "data" / "out" / "build_manifest.json").is_file()
    with zipfile.ZipFile(fetched.archive) as archive:
        names = archive.namelist()
    assert f"toronto-election-results-dev-{sha[:7]}/data/out/people.parquet" in names


def test_a_tag_must_point_at_the_pinned_commit(build_repo, tmp_path):
    repo, sha = build_repo
    git(repo, "tag", "results-2099-01-01.1", sha)
    fetch_build(BuildPin(str(repo), sha, "results-2099-01-01.1"), tmp_path / "ok")

    (repo / "CONTEXT.md").write_text("changed\n", encoding="utf-8")
    git(repo, "-c", "user.name=T", "-c", "user.email=t@invalid", "commit", "-qam", "later")
    git(repo, "tag", "results-2099-01-02.1")
    with pytest.raises(InputError, match="results-2099-01-02.1"):
        fetch_build(BuildPin(str(repo), sha, "results-2099-01-02.1"), tmp_path / "bad")


def test_verify_outputs_rejects_a_changed_file(build_repo, tmp_path):
    repo, sha = build_repo
    fetched = fetch_build(BuildPin(str(repo), sha), tmp_path / "cache")
    verify_outputs(fetched.root)
    target = fetched.root / "data" / "out" / "parties.parquet"
    target.write_bytes(target.read_bytes() + b"\0")
    with pytest.raises(InputError, match="parties.parquet"):
        verify_outputs(fetched.root)


def test_verify_outputs_rejects_a_file_the_manifest_does_not_list(build_repo, tmp_path):
    repo, sha = build_repo
    fetched = fetch_build(BuildPin(str(repo), sha), tmp_path / "cache")
    (fetched.root / "data" / "out" / "extra.csv").write_text("a\n1\n", encoding="utf-8")
    with pytest.raises(InputError, match="extra.csv"):
        verify_outputs(fetched.root)


def test_verify_outputs_returns_the_manifest(build_repo, tmp_path):
    repo, sha = build_repo
    fetched = fetch_build(BuildPin(str(repo), sha), tmp_path / "cache")
    manifest = verify_outputs(fetched.root)
    expected = json.loads(
        (fetched.root / "data" / "out" / "build_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest == expected
