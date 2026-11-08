"""Finding, downloading, checking and caching a version."""

from __future__ import annotations

import json
import zipfile

import pandas as pd
import pytest
from conftest import PACKAGE, REGISTRY, VERSION

import torontoelections as te
from torontoelections import LoaderError


def test_versions_lists_the_registry():
    table = te.versions()
    assert table.version.tolist() == [VERSION]
    assert {"version", "published", "doi", "build_commit"} <= set(table.columns)


def test_download_checks_and_caches_a_version():
    folder = te.download(VERSION)
    assert (folder / "datapackage.json").is_file()
    assert folder.is_relative_to(te.cache_dir())
    assert te.download(VERSION) == folder


def test_a_package_that_does_not_match_its_published_checksum_is_refused(
    registry_copy, monkeypatch
):
    package = registry_copy / PACKAGE.name
    data = bytearray(package.read_bytes())
    data[100] ^= 0xFF
    package.write_bytes(bytes(data))
    monkeypatch.setenv("TORONTO_ELECTIONS_REGISTRY", str(registry_copy / "versions.csv"))
    with pytest.raises(LoaderError, match="SHA-256"):
        te.download(VERSION)


def test_a_changed_data_file_is_refused(tmp_path):
    folder = tmp_path / "pkg"
    with zipfile.ZipFile(PACKAGE) as archive:
        archive.extractall(folder)
    root = next(folder.iterdir())
    parquet = root / "data" / "parties.parquet"
    parquet.write_bytes(parquet.read_bytes() + b"\0")
    with pytest.raises(LoaderError, match="parties.parquet"):
        te.parties(version=root)


def test_a_newer_package_schema_asks_for_a_newer_loader(tmp_path):
    folder = tmp_path / "pkg"
    with zipfile.ZipFile(PACKAGE) as archive:
        archive.extractall(folder)
    root = next(folder.iterdir())
    descriptor = json.loads((root / "datapackage.json").read_text(encoding="utf-8"))
    descriptor["schema_version"] = "2.0.0"
    (root / "datapackage.json").write_text(json.dumps(descriptor), encoding="utf-8")
    with pytest.raises(LoaderError, match="newer release of toronto-elections"):
        te.parties(version=root)


def test_a_local_zip_can_be_loaded_without_the_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("TORONTO_ELECTIONS_REGISTRY", str(tmp_path / "missing.csv"))
    assert len(te.parties(version=PACKAGE)) > 0


def test_without_a_version_the_newest_is_used_and_named_once(capsys):
    te.parties()
    te.contests()
    err = capsys.readouterr().err
    assert err.count(f"version {VERSION}") == 1
    assert f"version='{VERSION}'" in err


def test_the_first_load_prints_the_citation_once(capsys):
    te.parties(version=VERSION)
    te.parties(version=VERSION)
    assert capsys.readouterr().err.count("Toronto Election Results (Version") == 1


def test_an_empty_registry_says_nothing_is_published(tmp_path, monkeypatch):
    empty = tmp_path / "versions.csv"
    empty.write_text(REGISTRY.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    monkeypatch.setenv("TORONTO_ELECTIONS_REGISTRY", str(empty))
    with pytest.raises(LoaderError, match="No version"):
        te.candidacies()


def test_an_unreachable_registry_falls_back_to_the_cached_copy(monkeypatch):
    te.versions()
    monkeypatch.setenv("TORONTO_ELECTIONS_REGISTRY", "https://example.invalid/versions.csv")
    with pytest.warns(UserWarning, match="cached copy"):
        assert te.versions().version.tolist() == [VERSION]


def test_an_unknown_version_is_named():
    with pytest.raises(LoaderError, match="results-1999-01-01.1"):
        te.parties(version="results-1999-01-01.1")


def test_clear_cache_removes_a_version():
    folder = te.download(VERSION)
    te.clear_cache(VERSION)
    assert not folder.exists()


def test_newest_is_the_latest_publication_date():
    table = pd.DataFrame(
        {
            "version": ["results-2026-11-30.1", "results-2027-01-15.1"],
            "published": ["2026-12-01", "2027-01-20"],
        }
    )
    assert te._package.newest(table) == "results-2027-01-15.1"
