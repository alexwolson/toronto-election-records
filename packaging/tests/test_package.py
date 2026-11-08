"""End-to-end: build the package and the supplement from the fixture build, then check them."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from conftest import FIXTURE, git

from te_package.assemble import build_package
from te_package.build_input import BuildPin
from te_package.checks import (
    check_audited_links,
    check_datapackage,
    check_formats_agree,
    check_no_contact_details,
)
from te_package.codebook import load_codebook

CODEBOOK = load_codebook()
TABLES = [t.name for t in CODEBOOK.tables]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("e2e")
    repo = root / "toronto-election-results"
    shutil.copytree(FIXTURE, repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=T", "-c", "user.email=t@invalid", "commit", "-qm", "Fixture")
    sha = git(repo, "rev-parse", "HEAD")
    result = build_package(BuildPin(str(repo), sha), cache=root / "cache", out_dir=root / "dist")
    return result, sha


def _names(path: Path) -> set[str]:
    """Names inside the ZIP, below the one folder that holds everything, named like the ZIP."""

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    prefix = path.stem + "/"
    assert all(name.startswith(prefix) for name in names)
    return {name.removeprefix(prefix) for name in names}


def test_the_package_is_named_for_its_version(built):
    result, sha = built
    assert result.package_zip.name == f"toronto-election-records-dev-{sha[:7]}.zip"
    assert result.supplement_zip.name == f"toronto-election-records-dev-{sha[:7]}-provenance.zip"


def test_the_package_holds_the_documents_and_every_table_in_four_formats(built):
    result, _ = built
    names = _names(result.package_zip)
    for doc in (
        "README.md",
        "CODEBOOK.md",
        "CODEBOOK.pdf",
        "CHANGELOG.md",
        "KNOWN_ISSUES.md",
        "VALIDATION.md",
        "DATASHEET.md",
        "CITATION.cff",
        "LICENSE",
        "datapackage.json",
        "data/districts.gpkg",
    ):
        assert doc in names
    for table in TABLES:
        for ext in ("csv", "parquet", "dta", "rds"):
            assert f"data/{table}.{ext}" in names
    assert not any("endorse" in name for name in names)


def test_the_supplement_holds_the_audit_trail_and_the_build(built):
    result, sha = built
    names = _names(result.supplement_zip)
    for item in (
        "README.md",
        "candidacy_person_links.csv",
        "person_external_ids.csv",
        "build_manifest.json",
        "lineage/candidacies.csv",
        "lineage/contests.csv",
        "lineage/office_tenures.csv",
        "lineage/districts.csv",
        "verification/link-audit-2026-11-07.md",
        "verification/link-audit-2026-11-07/joins_results.csv",
        "provenance.md",
        "build-notes.md",
        "adr/0001-example.md",
        "CONTEXT.md",
        f"toronto-election-results-dev-{sha[:7]}.zip",
    ):
        assert item in names, item
    assert not any("research" in name for name in names)


def test_datapackage_lists_every_data_file_with_its_checksum(built):
    result, _ = built
    descriptor = json.loads((result.package_dir / "datapackage.json").read_text(encoding="utf-8"))
    assert descriptor["schema_version"] == CODEBOOK.schema_version
    assert descriptor["version"] == result.version
    files = []
    for resource in descriptor["resources"]:
        files.append(resource)
        files.extend(resource.get("formats", {}).values())
    for entry in files:
        path = result.package_dir / entry["path"]
        assert entry["hash"] == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["bytes"] == path.stat().st_size
    assert check_datapackage(result.package_dir, CODEBOOK) == []


def test_the_licence_carries_the_build_source_attributions(built):
    result, _ = built
    licence = (result.package_dir / "LICENSE").read_text(encoding="utf-8")
    assert "Creative Commons Attribution 4.0" in licence
    assert "Statistics Canada Open Licence" in licence


def test_documents_state_the_version_and_counts(built):
    result, _ = built
    readme = (result.package_dir / "README.md").read_text(encoding="utf-8")
    rows = len(pd.read_parquet(result.package_dir / "data" / "candidacies.parquet"))
    assert result.version in readme
    assert f"{rows:,}" in readme
    assert "$" not in readme.replace("$ ", "")


def test_the_four_formats_agree_until_one_is_changed(built, tmp_path):
    result, _ = built
    assert check_formats_agree(result.package_dir, CODEBOOK) == []
    copy = tmp_path / "pkg"
    shutil.copytree(result.package_dir, copy)
    dta = copy / "data" / "parties.dta"
    frame = pd.read_stata(dta)
    frame.loc[0, "canonical_name"] = "Changed"
    frame.to_stata(dta, write_index=False, version=118)
    problems = check_formats_agree(copy, CODEBOOK)
    assert any("parties.dta" in p for p in problems)


def test_contact_details_are_found(tmp_path):
    clean = tmp_path / "clean.csv"
    clean.write_text(
        "name,votes,url\nJane Doe,1234,https://a.ca/2016-councillor-ward-2.xlsx\n", encoding="utf-8"
    )
    assert check_no_contact_details([clean]) == []
    for text in (
        "write to jane@example.ca",
        "call 416-555-0199",
        "postal code M5V 3L9",
        "lives at 100 Queen Street West",
    ):
        dirty = tmp_path / "dirty.md"
        dirty.write_text(text, encoding="utf-8")
        assert check_no_contact_details([dirty]), text


def test_the_package_holds_no_contact_details(built):
    result, _ = built
    files = [
        p for p in result.package_dir.rglob("*") if p.suffix in {".csv", ".md", ".json", ".cff"}
    ]
    assert check_no_contact_details(files) == []


def test_audited_links_must_be_the_links_in_the_build():
    manifest = {
        "artifacts": [
            {"local_path": "data/out/candidacy_person_links.csv", "sha256": "a" * 64},
        ]
    }
    assert check_audited_links(manifest, "a" * 64) == []
    assert check_audited_links(manifest, "b" * 64)


def test_posix_cksum_matches_the_cksum_command(tmp_path):
    import subprocess

    from te_package.checks import posix_cksum

    for size in (0, 1, 1000, 70000):
        path = tmp_path / f"f{size}"
        path.write_bytes(bytes((i * 7 + size) % 256 for i in range(size)))
        expected = subprocess.run(["cksum", str(path)], capture_output=True, text=True, check=True)
        crc, length = expected.stdout.split()[:2]
        assert posix_cksum(path) == (int(crc), int(length))


def test_checksums_csv_lists_every_file_with_its_size_sha256_and_cksum(built):
    from te_package.checks import posix_cksum

    result, _ = built
    table = pd.read_csv(result.package_dir / "checksums.csv", dtype={"path": str})
    files = sorted(
        str(p.relative_to(result.package_dir))
        for p in result.package_dir.rglob("*")
        if p.is_file() and p.name != "checksums.csv"
    )
    assert table.columns.tolist() == ["path", "bytes", "sha256", "cksum"]
    assert table.path.tolist() == files
    for row in table.itertuples():
        path = result.package_dir / row.path
        assert row.bytes == path.stat().st_size
        assert row.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
        assert row.cksum == posix_cksum(path)[0]


def test_stata_files_read_back_with_readstat(built):
    """ReadStat, an implementation of the format independent of pandas, reads each .dta file
    as Stata will: format 118, the codebook's names and labels, false/true value labels on
    booleans, %td dates, and the Parquet file's values."""

    import pyarrow.parquet as pq
    import pyreadstat

    result, _ = built
    for table in CODEBOOK.tables:
        path = result.package_dir / "data" / f"{table.name}.dta"
        assert path.read_bytes()[:50].startswith(b"<stata_dta><header><release>118</release>")
        frame, meta = pyreadstat.read_dta(str(path), apply_value_formats=False)
        assert meta.column_names == [c.name for c in table.columns], table.name
        assert meta.column_labels == [c.label for c in table.columns], table.name
        reference = pq.read_table(result.package_dir / "data" / f"{table.name}.parquet").to_pydict()
        for column in table.columns:
            name = column.name
            got = frame[name].tolist()
            if column.type == "boolean":
                label_set = meta.variable_to_label[name]
                assert meta.value_labels[label_set] == {0: "false", 1: "true"}, name
                got = [None if pd.isna(v) else bool(v) for v in got]
            elif column.type == "date":
                assert meta.original_variable_types[name] == "%td", name
                got = [None if pd.isna(v) else pd.Timestamp(v).date() for v in got]
            elif column.type == "string":
                got = [None if v == "" else v for v in got]
            elif column.type == "integer":
                got = [None if pd.isna(v) else int(v) for v in got]
            else:
                got = [None if pd.isna(v) else float(v) for v in got]
            assert got == reference[name], (table.name, name)


def test_a_release_name_with_a_dot_keeps_both_zip_names(tmp_path):
    from te_package.assemble import _zip

    for name in (
        "toronto-election-records-results-2026-11-30.1",
        "toronto-election-records-results-2026-11-30.1-provenance",
    ):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "x.txt").write_text("x", encoding="utf-8")
        assert _zip(folder).name == f"{name}.zip"
