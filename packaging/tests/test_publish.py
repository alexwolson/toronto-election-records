"""Publishing: a Zenodo draft that holds both ZIPs, the registry row, and the Dataverse folder."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from conftest import FIXTURE, git

from te_package.build_input import BuildPin
from te_package.checks import posix_cksum
from te_package.codebook import REPO_ROOT
from te_package.publish import (
    PublishError,
    Zenodo,
    dataverse_folder,
    publish_draft,
    register,
)

BASE = "https://sandbox.zenodo.org"
TOKEN = "not-a-real-token"
TAG = "results-2099-01-01.1"


class Response:
    def __init__(self, status: int, payload=None, content: bytes = b""):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        return self._payload


class FakeZenodo:
    """Answers the deposit API as Zenodo does, and records every request."""

    def __init__(self, record: dict | None = None, downloads: dict | None = None):
        self.calls: list[tuple[str, str, dict]] = []
        self.uploads: dict[str, int] = {}
        self.record = record
        self.downloads = downloads or {}

    def _draft(self, number: int, files: list) -> dict:
        return {
            "id": number,
            "links": {
                "bucket": f"{BASE}/api/files/bucket-{number}",
                "html": f"{BASE}/deposit/{number}",
            },
            "metadata": {"prereserve_doi": {"doi": f"10.5072/zenodo.{number}", "recid": number}},
            "files": files,
        }

    def request(self, method: str, url: str, **kwargs) -> Response:
        self.calls.append((method, url, kwargs))
        path = url.removeprefix(BASE)
        if method == "POST" and path == "/api/deposit/depositions":
            return Response(201, self._draft(11, []))
        if method == "POST" and path == "/api/deposit/depositions/5/actions/newversion":
            latest = f"{BASE}/api/deposit/depositions/12"
            return Response(201, {"id": 5, "links": {"latest_draft": latest}})
        if method == "GET" and path == "/api/deposit/depositions/12":
            return Response(200, self._draft(12, [{"id": "old-file", "filename": "old.zip"}]))
        if method == "DELETE" and path.startswith("/api/deposit/depositions/12/files/"):
            return Response(204)
        if method == "PUT" and path.startswith("/api/files/bucket-"):
            self.uploads[path.rsplit("/", 1)[1]] = len(kwargs["data"].read())
            return Response(201, {})
        if method == "PUT" and path.startswith("/api/deposit/depositions/"):
            return Response(200, {"metadata": kwargs["json"]["metadata"]})
        if method == "GET" and url in self.downloads:
            return Response(200, content=self.downloads[url])
        if method == "GET" and path.startswith("/api/records/") and self.record is not None:
            return Response(200, self.record)
        return Response(404, {"message": f"no route for {method} {path}"})


@pytest.fixture(scope="module")
def tagged_build(tmp_path_factory):
    root = tmp_path_factory.mktemp("publish")
    repo = root / "toronto-election-results"
    shutil.copytree(FIXTURE, repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=T", "-c", "user.email=t@invalid", "commit", "-qm", "Fixture")
    git(repo, "tag", TAG)
    sha = git(repo, "rev-parse", "HEAD")
    links = (FIXTURE / "data" / "out" / "candidacy_person_links.csv").read_bytes()
    return BuildPin(str(repo), sha, TAG), hashlib.sha256(links).hexdigest(), root


def _publish(tagged_build, fake, previous_id):
    pin, audited, root = tagged_build
    out = root / f"dist-{previous_id}"
    if out.exists():
        shutil.rmtree(out)
    client = Zenodo(BASE, TOKEN, session=fake)
    return publish_draft(pin, root / "cache", out, audited, client, previous_id)


def test_a_development_build_cannot_be_published(tmp_path):
    client = Zenodo(BASE, TOKEN, session=FakeZenodo())
    with pytest.raises(PublishError, match="development build"):
        publish_draft(BuildPin("repo", "a" * 40), tmp_path, tmp_path, None, client, None)


def test_a_first_version_reserves_a_doi_builds_with_it_and_uploads_both_zips(tagged_build):
    fake = FakeZenodo()
    result = _publish(tagged_build, fake, None)
    assert result.draft.doi == "10.5072/zenodo.11"
    package = result.built.package_dir
    assert "https://doi.org/10.5072/zenodo.11" in (package / "README.md").read_text("utf-8")
    assert 'doi: "10.5072/zenodo.11"' in (package / "CITATION.cff").read_text("utf-8")
    assert set(fake.uploads) == {
        f"toronto-election-records-{TAG}.zip",
        f"toronto-election-records-{TAG}-provenance.zip",
    }
    metadata = next(
        kw["json"]["metadata"] for m, u, kw in fake.calls if m == "PUT" and "json" in kw
    )
    assert metadata["version"] == TAG
    assert metadata["upload_type"] == "dataset"
    assert metadata["license"] == "cc-by-4.0"
    assert metadata["creators"][0] == {
        "name": "Olson, Alex",
        "affiliation": "University of Toronto",
        "orcid": "0000-0002-6593-2779",
    }
    assert metadata["prereserve_doi"] == {"doi": "10.5072/zenodo.11", "recid": 11}
    assert not any(url.endswith("/actions/publish") for _, url, _ in fake.calls)


def test_a_new_version_drops_the_files_it_inherits(tagged_build):
    fake = FakeZenodo()
    result = _publish(tagged_build, fake, 5)
    assert result.draft.id == 12
    assert ("DELETE", f"{BASE}/api/deposit/depositions/12/files/old-file") in [
        (m, u) for m, u, _ in fake.calls
    ]
    assert all("bucket-12" in u for m, u, _ in fake.calls if m == "PUT" and "/api/files/" in u)


def test_the_token_goes_only_in_the_authorization_header(tagged_build, capsys):
    fake = FakeZenodo()
    _publish(tagged_build, fake, None)
    for _, url, kwargs in fake.calls:
        assert TOKEN not in url
        assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
    printed = capsys.readouterr()
    assert TOKEN not in printed.out + printed.err


def test_register_adds_the_published_version_to_the_registry(tmp_path):
    fixture_zip = next((REPO_ROOT / "fixtures").glob("toronto-election-records-*.zip"))
    version = fixture_zip.stem.removeprefix("toronto-election-records-")
    url = f"{BASE}/api/records/77/files/{fixture_zip.name}/content"
    record = {
        "id": 77,
        "doi": "10.5072/zenodo.77",
        "links": {"html": f"{BASE}/records/77"},
        "metadata": {"version": version, "publication_date": "2099-01-02"},
        "files": [
            {"key": fixture_zip.name, "size": fixture_zip.stat().st_size, "links": {"self": url}}
        ],
    }
    registry = tmp_path / "versions.csv"
    shutil.copy2(REPO_ROOT / "versions.csv", registry)
    fake = FakeZenodo(record=record, downloads={url: fixture_zip.read_bytes()})
    row = register(BASE, 77, registry, session=fake)
    table = pd.read_csv(registry, dtype=str)
    assert table.to_dict("records") == [{k: str(v) for k, v in row.items()}]
    crc, length = posix_cksum(fixture_zip)
    assert row["version"] == version
    assert row["doi"] == "10.5072/zenodo.77"
    assert row["record_url"] == f"{BASE}/records/77"
    assert row["package_url"] == url
    assert row["package_bytes"] == length
    assert row["package_cksum"] == crc
    assert row["package_sha256"] == hashlib.sha256(fixture_zip.read_bytes()).hexdigest()
    assert row["schema_version"] == "1.0.0"
    with pytest.raises(PublishError, match="already"):
        register(BASE, 77, registry, session=fake)


def _raw(tmp_path: Path) -> tuple[dict, Path]:
    raw = tmp_path / "build" / "data" / "raw"
    (raw / "ckan").mkdir(parents=True)
    (raw / "results").mkdir()
    (raw / "federal").mkdir()
    files = {
        "data/raw/results/2022-results.zip": (
            b"results",
            "https://ckan0.cf.opendata.inter.prod-toronto.ca/a.zip",
        ),
        "data/raw/ckan/roster.json": (
            b'{"contact": "someone@example.ca"}',
            "https://ckan0.cf.opendata.inter.prod-toronto.ca/b",
        ),
        "data/raw/federal/elections-canada.csv": (b"federal", "https://www.elections.ca/c.csv"),
    }
    sources = []
    for local, (data, url) in files.items():
        path = tmp_path / "build" / local
        path.write_bytes(data)
        sources.append(
            {
                "local_path": local,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "source_url": url,
            }
        )
    return {"sources": sources}, tmp_path / "build"


def test_dataverse_folder_holds_the_zips_and_the_citys_raw_files_without_contact_details(tmp_path):
    manifest, build_root = _raw(tmp_path)
    package = tmp_path / "toronto-election-records-v.zip"
    supplement = tmp_path / "toronto-election-records-v-provenance.zip"
    for path in (package, supplement):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("x.txt", "x")
    out = tmp_path / "deposit"
    left_out = dataverse_folder(
        package, supplement, manifest, build_root, out, "v", "10.5281/zenodo.1"
    )
    assert sorted(p.name for p in out.iterdir()) == sorted(
        ["DATAVERSE.md", "raw", package.name, supplement.name]
    )
    assert (out / "raw" / "results" / "2022-results.zip").read_bytes() == b"results"
    assert not (out / "raw" / "ckan" / "roster.json").exists()
    assert not (out / "raw" / "federal").exists()
    assert left_out == ["data/raw/ckan/roster.json"]
    sources = pd.read_csv(out / "raw" / "SOURCES.csv")
    assert sources.path.tolist() == ["results/2022-results.zip"]
    form = (out / "DATAVERSE.md").read_text("utf-8")
    assert "https://doi.org/10.5281/zenodo.1" in form
    assert "Open Government Licence – Toronto" in form


def test_dataverse_folder_refuses_a_raw_file_that_does_not_match_the_manifest(tmp_path):
    manifest, build_root = _raw(tmp_path)
    (build_root / "data" / "raw" / "results" / "2022-results.zip").write_bytes(b"changed")
    package = tmp_path / "p.zip"
    package.write_bytes(b"")
    with pytest.raises(PublishError, match="2022-results.zip"):
        dataverse_folder(
            package, package, manifest, build_root, tmp_path / "d", "v", "10.5281/zenodo.1"
        )
