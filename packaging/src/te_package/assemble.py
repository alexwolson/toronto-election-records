"""Build the user package and the provenance supplement from one pinned build."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv

from te_package.build_input import BuildPin, fetch_build, sha256, verify_outputs
from te_package.checks import checksum_rows, run_checks
from te_package.codebook import Codebook, load_codebook, render_markdown, table_schema
from te_package.documents import render, template_values
from te_package.tables import UserTables, make_tables, read_build
from te_package.writers import FORMATS, write_shapes, write_table

PACKAGE_DOCUMENTS = (
    "README.md",
    "CHANGELOG.md",
    "KNOWN_ISSUES.md",
    "VALIDATION.md",
    "DATASHEET.md",
)
MEDIA_TYPES = {
    "csv": "text/csv",
    "parquet": "application/vnd.apache.parquet",
    "dta": "application/x-stata-dta",
    "rds": "application/x-r-data",
}


class AssemblyError(Exception):
    """The package cannot be assembled."""


@dataclass(frozen=True)
class Built:
    version: str
    package_dir: Path
    package_zip: Path
    supplement_zip: Path


def _file_entry(package_dir: Path, path: Path) -> dict:
    return {
        "path": str(path.relative_to(package_dir)),
        "bytes": path.stat().st_size,
        "hash": "sha256:" + sha256(path),
    }


def _datapackage(
    package_dir: Path, codebook: Codebook, pin: BuildPin, files: dict, shapes: Path, created: str
) -> dict:
    resources = []
    for table in codebook.tables:
        paths = files[table.name]
        resource = {
            "name": table.name,
            "title": table.title,
            "description": f"{table.grain} {table.description}",
            **_file_entry(package_dir, paths["csv"]),
            "format": "csv",
            "mediatype": MEDIA_TYPES["csv"],
            "encoding": "utf-8",
            "schema": table_schema(table),
            "formats": {
                fmt: {**_file_entry(package_dir, paths[fmt]), "mediatype": MEDIA_TYPES[fmt]}
                for fmt in FORMATS
                if fmt != "csv"
            },
        }
        resources.append(resource)
    resources.append(
        {
            "name": "district_shapes",
            "title": "District shapes",
            "description": "The shape of every district in `districts` that has one, in EPSG:4326.",
            **_file_entry(package_dir, shapes),
            "format": "gpkg",
            "mediatype": "application/geopackage+sqlite3",
        }
    )
    return {
        "name": "toronto-election-results",
        "title": "Toronto Election Results",
        "version": pin.version,
        "schema_version": codebook.schema_version,
        "created": created,
        "licenses": [
            {
                "name": "CC-BY-4.0",
                "title": "Creative Commons Attribution 4.0 International",
                "path": "https://creativecommons.org/licenses/by/4.0/",
            }
        ],
        "build": {"repository": pin.repository, "commit": pin.commit, "tag": pin.tag},
        "resources": resources,
    }


def _pdf(markdown: Path, pdf: Path) -> None:
    result = subprocess.run(
        ["pandoc", str(markdown), "-o", str(pdf), "--pdf-engine=typst", "-V", "papersize=a4"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssemblyError(f"pandoc could not make {pdf.name}: {result.stderr.strip()}")


def _fresh_dir(path: Path, parent: Path) -> Path:
    """Empty a folder the build owns. Only a direct child of `parent` is ever removed."""

    if path.parent != parent:
        raise AssemblyError(f"refusing to clear {path}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def _zip(folder: Path) -> Path:
    target = folder.with_suffix(".zip")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            archive.write(path, f"{folder.name}/{path.relative_to(folder)}")
    return target


def _supplement(
    folder: Path, root: Path, archive: Path, made: UserTables, values: dict[str, str]
) -> None:
    out, docs = root / "data" / "out", root / "docs"
    (folder / "README.md").write_text(render("SUPPLEMENT_README.md", values), encoding="utf-8")
    for name in ("candidacy_person_links.csv", "person_external_ids.csv", "build_manifest.json"):
        shutil.copy2(out / name, folder / name)
    (folder / "lineage").mkdir()
    for name, frame in made.lineage.items():
        pacsv.write_csv(
            pa.Table.from_pandas(frame, preserve_index=False), folder / "lineage" / f"{name}.csv"
        )
    shutil.copytree(docs / "verification", folder / "verification")
    shutil.copytree(docs / "adr", folder / "adr")
    for name in ("provenance.md", "build-notes.md"):
        shutil.copy2(docs / name, folder / name)
    shutil.copy2(root / "CONTEXT.md", folder / "CONTEXT.md")
    shutil.copy2(archive, folder / archive.name)


def build_package(
    pin: BuildPin,
    cache: Path,
    out_dir: Path,
    audited_links_sha256: str | None = None,
) -> Built:
    if pin.is_release and not audited_links_sha256:
        raise AssemblyError("a release needs the SHA-256 of the links file the audit covered")
    fetched = fetch_build(pin, cache)
    manifest = verify_outputs(fetched.root)
    codebook = load_codebook()
    build = read_build(fetched.root / "data" / "out")
    made = make_tables(build, codebook)
    values = template_values(made, manifest, pin, codebook, fetched.root, audited_links_sha256)
    stamp = dt.datetime.fromisoformat(str(manifest["generated_at"]).replace("Z", "+00:00"))

    out_dir.mkdir(parents=True, exist_ok=True)
    package = _fresh_dir(out_dir / f"toronto-election-records-{pin.version}", out_dir)
    data = package / "data"
    files = {
        t.name: write_table(made.tables[t.name], t, data, stamp.replace(tzinfo=None))
        for t in codebook.tables
    }
    shapes = data / "districts.gpkg"
    write_shapes(made.shapes, shapes)
    descriptor = _datapackage(package, codebook, pin, files, shapes, values["build_date"])
    (package / "datapackage.json").write_text(
        json.dumps(descriptor, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    codebook_md = package / "CODEBOOK.md"
    codebook_md.write_text(render_markdown(codebook, pin.version), encoding="utf-8")
    _pdf(codebook_md, package / "CODEBOOK.pdf")
    for name in PACKAGE_DOCUMENTS:
        (package / name).write_text(render(name, values), encoding="utf-8")
    (package / "CITATION.cff").write_text(render("CITATION.cff", values), encoding="utf-8")
    (package / "LICENSE").write_text(render("LICENSE", values), encoding="utf-8")
    # Written last, so it lists every other file; Stata's loader checks files with `cksum`.
    pd.DataFrame(checksum_rows(package)).to_csv(package / "checksums.csv", index=False)
    run_checks(package, codebook, made.tables, build, manifest, audited_links_sha256)

    supplement = _fresh_dir(out_dir / f"toronto-election-records-{pin.version}-provenance", out_dir)
    _supplement(supplement, fetched.root, fetched.archive, made, values)
    return Built(
        version=pin.version,
        package_dir=package,
        package_zip=_zip(package),
        supplement_zip=_zip(supplement),
    )
