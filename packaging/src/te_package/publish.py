"""Publish a version: a Zenodo draft that holds both ZIPs, the registry row, the Dataverse folder.

Publishing a Zenodo record cannot be undone, so `publish_draft` stops at a draft: it creates the
draft (a new version of the record when there is one), sets its metadata, reserves its DOI,
builds the package with that DOI in its README and citation, and uploads the package and the
provenance supplement. The maintainer reviews the draft on Zenodo and publishes it there. Then
`register` adds the published version to `versions.csv`, from the public record, so the loaders
find it.

The Zenodo token is read from the environment by the command line and sent only in the
Authorization header; it is never written or printed.

`dataverse_folder` assembles the Dataverse deposit: both ZIPs, the City of Toronto's raw files
(which the Open Government Licence – Toronto lets anyone redistribute) checked against the build
manifest, without any file that holds an email address, and the values for the deposit form.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

from te_package.assemble import Built, build_package
from te_package.build_input import BuildPin, sha256
from te_package.checks import posix_cksum

ZENODO = {"live": "https://zenodo.org", "sandbox": "https://sandbox.zenodo.org"}
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
CITY_PORTAL_HOST = "ckan0.cf.opendata.inter.prod-toronto.ca"
CITY_LICENCE = "Open Government Licence – Toronto"
EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DESCRIPTION = (
    "<p>Candidates and results of the municipal, school board trustee, federal and provincial "
    "elections held within the City of Toronto, from the last general elections before "
    "amalgamation (1993 federal, 1994 municipal, 1995 Ontario) through the 2026 municipal general "
    "election, with one row per candidacy and evidence-backed links that join each person's runs "
    "for office.</p>"
    "<p><code>toronto-election-records-VERSION.zip</code> is the dataset: eight tables in CSV, "
    "Parquet, Stata and R formats, district shapes, a codebook, and notes on validation and known "
    "issues. <code>toronto-election-records-VERSION-provenance.zip</code> holds the full Person "
    "link table, the verification reports and the code that built this version.</p>"
    "<p>The R package torontoelections and the Python package toronto-elections load any version "
    "and check it against its checksums.</p>"
)
KEYWORDS = [
    "Toronto",
    "elections",
    "municipal elections",
    "school board trustees",
    "Canadian federal elections",
    "Ontario elections",
    "election results",
]


class PublishError(Exception):
    """A version cannot be published or registered."""


@dataclass(frozen=True)
class Draft:
    id: int
    bucket: str
    html: str
    reserved: dict | None

    @property
    def doi(self) -> str:
        if not self.reserved or not self.reserved.get("doi"):
            raise PublishError("Zenodo has not reserved a DOI for the draft")
        return self.reserved["doi"]


@dataclass(frozen=True)
class Published:
    draft: Draft
    built: Built


class Zenodo:
    """The parts of Zenodo's deposit and records API that publishing uses."""

    def __init__(self, base: str, token: str | None, session=None):
        self.base = base.rstrip("/")
        self._token = token
        self._session = session or requests.Session()

    def call(self, method: str, url: str, **kwargs):
        url = url if url.startswith("http") else self.base + url
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        response = self._session.request(method, url, headers=headers, timeout=600, **kwargs)
        if response.status_code not in (200, 201, 202, 204):
            raise PublishError(
                f"Zenodo answered {response.status_code} to {method} {url}: {response.text[:300]}"
            )
        return response

    def new_draft(self, previous_id: int | None) -> Draft:
        """A draft for a first version, or a new version of a record without its old files."""

        if previous_id is None:
            body = {"metadata": {"prereserve_doi": True}}
            deposit = self.call("POST", "/api/deposit/depositions", json=body).json()
        else:
            path = f"/api/deposit/depositions/{previous_id}/actions/newversion"
            latest = self.call("POST", path).json()["links"]["latest_draft"]
            deposit = self.call("GET", latest).json()
            for file in deposit.get("files", []):
                self.call("DELETE", f"/api/deposit/depositions/{deposit['id']}/files/{file['id']}")
        return Draft(
            id=deposit["id"],
            bucket=deposit["links"]["bucket"],
            html=deposit["links"]["html"],
            reserved=deposit.get("metadata", {}).get("prereserve_doi") or None,
        )

    def set_metadata(self, draft: Draft, metadata: dict) -> Draft:
        """Set the draft's metadata, reserving a DOI if it has none; return the draft."""

        reserved = draft.reserved if draft.reserved else True
        body = {"metadata": {**metadata, "prereserve_doi": reserved}}
        answer = self.call("PUT", f"/api/deposit/depositions/{draft.id}", json=body).json()
        return replace(draft, reserved=answer["metadata"].get("prereserve_doi"))

    def upload(self, draft: Draft, path: Path) -> None:
        with path.open("rb") as handle:
            self.call("PUT", f"{draft.bucket}/{path.name}", data=handle)


def zenodo_metadata(version: str, published: str, commit: str) -> dict:
    return {
        "upload_type": "dataset",
        "title": "Toronto Election Results",
        "version": version,
        "publication_date": published,
        "creators": [
            {
                "name": "Olson, Alex",
                "affiliation": "University of Toronto",
                "orcid": "0000-0002-6593-2779",
            },
            {"name": "Elliott, Matt"},
        ],
        "description": DESCRIPTION,
        "license": "cc-by-4.0",
        "keywords": KEYWORDS,
        "related_identifiers": [
            {
                "relation": "isDerivedFrom",
                "identifier": f"https://github.com/alexwolson/toronto-election-results/tree/{commit}",
                "resource_type": "software",
            },
            {
                "relation": "isSupplementedBy",
                "identifier": "https://github.com/alexwolson/toronto-election-records",
                "resource_type": "software",
            },
        ],
    }


def publish_draft(
    pin: BuildPin,
    cache: Path,
    out_dir: Path,
    audited_links_sha256: str | None,
    client: Zenodo,
    previous_id: int | None,
    published: str | None = None,
) -> Published:
    """Make a Zenodo draft of the pinned build with both ZIPs uploaded. It is not published."""

    if not pin.is_release:
        raise PublishError(
            "a development build cannot be published; pin a tagged build in build.toml"
        )
    published = published or dt.date.today().isoformat()
    draft = client.new_draft(previous_id)
    draft = client.set_metadata(draft, zenodo_metadata(pin.version, published, pin.commit))
    built = build_package(pin, cache, out_dir, audited_links_sha256, doi=draft.doi)
    client.upload(draft, built.package_zip)
    client.upload(draft, built.supplement_zip)
    return Published(draft=draft, built=built)


def _descriptor(package: Path) -> dict:
    with zipfile.ZipFile(package) as archive:
        name = next(
            n for n in archive.namelist() if n.count("/") == 1 and n.endswith("/datapackage.json")
        )
        return json.loads(archive.read(name))


def register(base: str, record_id: int, registry: Path, session=None) -> dict:
    """Add a published Zenodo record to the registry, from its public metadata and files."""

    client = Zenodo(base, None, session)
    record = client.call("GET", f"/api/records/{record_id}").json()
    version = record["metadata"]["version"]
    table = pd.read_csv(registry, dtype=str, keep_default_na=False)
    if version in set(table["version"]):
        raise PublishError(f"version {version} is already in {registry.name}")
    name = f"toronto-election-records-{version}.zip"
    entry = next((f for f in record["files"] if f["key"] == name), None)
    if entry is None:
        raise PublishError(f"record {record_id} has no file named {name}")
    url = entry["links"]["self"]
    with tempfile.TemporaryDirectory() as tmp:
        package = Path(tmp) / name
        package.write_bytes(client.call("GET", url).content)
        if package.stat().st_size != int(entry["size"]):
            raise PublishError(f"the download of {name} is not the size Zenodo lists")
        descriptor = _descriptor(package)
        if descriptor["version"] != version:
            raise PublishError(f"{name} holds version {descriptor['version']}, not {version}")
        crc, length = posix_cksum(package)
        row = {
            "version": version,
            "published": record["metadata"]["publication_date"],
            "doi": record.get("doi") or record["metadata"]["doi"],
            "record_url": record["links"]["html"],
            "build_commit": descriptor["build"]["commit"],
            "schema_version": descriptor["schema_version"],
            "package_url": url,
            "package_bytes": length,
            "package_sha256": sha256(package),
            "package_cksum": crc,
        }
    added = pd.DataFrame([row], columns=REGISTRY_COLUMNS).astype(str)
    table = pd.concat([table, added], ignore_index=True).sort_values(["published", "version"])
    table[REGISTRY_COLUMNS].to_csv(registry, index=False)
    return row


def _holds_email(path: Path) -> bool:
    """Search the file, and each member of a ZIP-based file (xlsx, zip), for an email address."""

    data = path.read_bytes()
    if EMAIL.search(data):
        return True
    if data[:2] == b"PK":
        with zipfile.ZipFile(path) as archive:
            return any(EMAIL.search(archive.read(name)) for name in archive.namelist())
    return False


def _form(version: str, doi: str) -> str:
    return f"""# Dataverse deposit: {version}

Values for the deposit form. The deposit mirrors version `{version}` of Toronto Election Results,
published on Zenodo at https://doi.org/{doi}, and adds the City of Toronto's raw files the build
reads.

- **Title:** Toronto Election Results, version {version}
- **Authors:** Olson, Alex (University of Toronto; ORCID 0000-0002-6593-2779); Elliott, Matt
- **Description:** Candidates and results of the municipal, school board trustee, federal and
  provincial elections held within the City of Toronto, from the last general elections before
  amalgamation through the 2026 municipal general election, with one row per candidacy and
  evidence-backed links that join each person's runs for office. This deposit mirrors version
  {version}, published on Zenodo (https://doi.org/{doi}), and adds the City of Toronto raw files
  the build reads.
- **Subject:** Social Sciences
- **Keywords:** {"; ".join(KEYWORDS)}
- **Related dataset:** Olson, A., & Elliott, M. ({version[8:12]}). *Toronto Election Results*
  (Version {version}) [Data set]. Zenodo. https://doi.org/{doi}
- **Licence:** CC BY 4.0 for the data and documentation. The raw files in `raw/` are the City of
  Toronto's, under the {CITY_LICENCE}.
- **Version:** {version}
- **Contact:** fill in on the form.
"""


def dataverse_folder(
    package_zip: Path,
    supplement_zip: Path,
    manifest: dict,
    build_root: Path,
    out_dir: Path,
    version: str,
    doi: str,
) -> list[str]:
    """Write the Dataverse deposit to `out_dir`; return the raw files left out for contact details.

    A raw file is copied only when its manifest URL is on the City's Open Data portal, it matches
    the manifest's SHA-256, and it holds no email address.
    """

    kept: list[dict] = []
    left_out: list[str] = []
    for record in manifest["sources"]:
        local = str(record["local_path"])
        if not local.startswith("data/raw/"):
            continue
        if urlparse(str(record.get("source_url", ""))).hostname != CITY_PORTAL_HOST:
            continue
        path = build_root / local
        if not path.is_file() or sha256(path) != record["sha256"]:
            raise PublishError(f"{local} is missing or does not match the build manifest")
        if _holds_email(path):
            left_out.append(local)
            continue
        kept.append(record)
    if out_dir.exists():
        raise PublishError(f"{out_dir} already exists")
    (out_dir / "raw").mkdir(parents=True)
    for archive in (package_zip, supplement_zip):
        shutil.copy2(archive, out_dir / archive.name)
    rows = []
    for record in kept:
        relative = str(record["local_path"]).removeprefix("data/raw/")
        target = out_dir / "raw" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(build_root / str(record["local_path"]), target)
        rows.append(
            {
                "path": relative,
                "source_url": record["source_url"],
                "sha256": record["sha256"],
                "bytes": record["bytes"],
                "licence": CITY_LICENCE,
            }
        )
    pd.DataFrame(rows, columns=["path", "source_url", "sha256", "bytes", "licence"]).to_csv(
        out_dir / "raw" / "SOURCES.csv", index=False
    )
    (out_dir / "DATAVERSE.md").write_text(_form(version, doi), encoding="utf-8")
    return left_out
