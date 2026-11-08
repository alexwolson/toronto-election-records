"""Checks the package must pass before it is zipped. Each returns a list of problems."""

from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from te_package.codebook import Codebook, arrow_schema, table_schema
from te_package.writers import run_r

R_CLASSES = {
    "string": "character",
    "integer": "integer",
    "number": "numeric",
    "boolean": "logical",
    "date": "Date",
}

CONTACT_PATTERNS = {
    "an email address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "a phone number": re.compile(r"(?<![\d/=_-])\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?![\d/])"),
    "a postal code": re.compile(
        r"\b[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z] ?\d[ABCEGHJ-NPRSTV-Z]\d\b"
    ),
    "a street address": re.compile(
        r"\b\d{1,5} (?:[A-Z][a-z]+ ){1,3}(?:Street|Avenue|Road|Boulevard|Drive|Crescent|Court"
        r"|Lane|Place|Parkway|Circle|Square|Terrace|Trail|St|Ave|Rd|Blvd|Dr|Cres)\b"
    ),
}


def _cksum_table() -> list[int]:
    table = []
    for i in range(256):
        crc = i << 24
        for _ in range(8):
            crc = (crc << 1) ^ 0x04C11DB7 if crc & 0x80000000 else crc << 1
        table.append(crc & 0xFFFFFFFF)
    return table


_CKSUM_TABLE = _cksum_table()


def posix_cksum(path: Path) -> tuple[int, int]:
    """The POSIX 1003.2 CRC of a file and its length, as `cksum` and Stata's `checksum` give."""

    crc, length, table = 0, 0, _CKSUM_TABLE
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            length += len(block)
            for byte in block:
                crc = ((crc << 8) & 0xFFFFFFFF) ^ table[(crc >> 24) ^ byte]
    remaining = length
    while remaining:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ table[(crc >> 24) ^ (remaining & 0xFF)]
        remaining >>= 8
    return (~crc) & 0xFFFFFFFF, length


def checksum_rows(package_dir: Path) -> list[dict]:
    """One row per file in the package but checksums.csv itself, in path order."""

    rows = []
    for path in sorted(p for p in package_dir.rglob("*") if p.is_file()):
        relative = str(path.relative_to(package_dir))
        if relative == "checksums.csv":
            continue
        crc, length = posix_cksum(path)
        rows.append({"path": relative, "bytes": length, "sha256": _sha256(path), "cksum": crc})
    return rows


def check_checksums_csv(package_dir: Path) -> list[str]:
    """checksums.csv lists every file of the package with its size, SHA-256 and POSIX cksum."""

    listed = pd.read_csv(package_dir / "checksums.csv", dtype={"path": str}).to_dict("records")
    if listed != checksum_rows(package_dir):
        return ["checksums.csv does not match the files in the package"]
    return []


class CheckError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("the package failed its checks:\n- " + "\n- ".join(problems))
        self.problems = problems


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=0.0)
    return a == b


def _columns(frame: pd.DataFrame) -> dict[str, list]:
    return {
        name: [
            None if (v is None or (isinstance(v, float) and math.isnan(v))) else v for v in values
        ]
        for name, values in frame.to_dict("list").items()
    }


def _read_dta(path: Path, codebook_table) -> dict[str, list]:
    frame = pd.read_stata(path, convert_categoricals=True)
    out = {}
    for column in codebook_table.columns:
        values = frame[column.name].tolist()
        if column.type == "string":
            values = [None if v == "" else v for v in values]
        elif column.type == "boolean":
            values = [None if pd.isna(v) else v == "true" for v in values]
        elif column.type == "integer":
            values = [None if pd.isna(v) else int(v) for v in values]
        elif column.type == "number":
            values = [None if pd.isna(v) else float(v) for v in values]
        elif column.type == "date":
            values = [None if pd.isna(v) else v.date() for v in values]
        out[column.name] = values
    return out


def _read_rds(path: Path, codebook_table, problems: list[str]) -> dict[str, list]:
    with tempfile.TemporaryDirectory() as tmp:
        parquet, info = Path(tmp) / "back.parquet", Path(tmp) / "info.json"
        run_r("inspect", str(path), str(parquet), str(info))
        meta = json.loads(info.read_text(encoding="utf-8"))
        values = pq.read_table(parquet).to_pydict()
    for column in codebook_table.columns:
        got = meta.get(column.name, {})
        if got.get("class") != R_CLASSES[column.type]:
            problems.append(f"{path.name}: {column.name} has R class {got.get('class')}")
        if got.get("label") != column.label:
            problems.append(f"{path.name}: {column.name} has the wrong label")
    return values


def check_formats_agree(package_dir: Path, codebook: Codebook) -> list[str]:
    """The CSV, Stata and R files of each table hold the values of its Parquet file."""

    problems: list[str] = []
    data = package_dir / "data"
    for table in codebook.tables:
        reference = pq.read_table(data / f"{table.name}.parquet").to_pydict()
        options = pacsv.ConvertOptions(
            column_types=arrow_schema(table),
            null_values=[""],
            strings_can_be_null=True,
            true_values=["true"],
            false_values=["false"],
        )
        copies = {
            f"{table.name}.csv": pacsv.read_csv(
                data / f"{table.name}.csv", convert_options=options
            ).to_pydict(),
            f"{table.name}.dta": _read_dta(data / f"{table.name}.dta", table),
            f"{table.name}.rds": _read_rds(data / f"{table.name}.rds", table, problems),
        }
        for name, copy in copies.items():
            if list(copy) != list(reference):
                problems.append(f"{name}: its columns differ from the Parquet file")
                continue
            for column, expected in reference.items():
                got = copy[column]
                if len(got) != len(expected):
                    problems.append(f"{name}: {column} has {len(got)} rows, not {len(expected)}")
                    continue
                bad = [
                    i for i, (a, b) in enumerate(zip(got, expected, strict=True)) if not _same(a, b)
                ]
                if bad:
                    problems.append(
                        f"{name}: {column} differs from the Parquet file in {len(bad)} rows"
                    )
    return problems


def check_values(tables: dict[str, pd.DataFrame], codebook: Codebook) -> list[str]:
    """Required columns have no nulls, listed values are respected and no string is empty."""

    problems = []
    for table in codebook.tables:
        frame = tables[table.name]
        if list(frame.columns) != [c.name for c in table.columns]:
            problems.append(f"{table.name}: its columns differ from the codebook")
            continue
        for column in table.columns:
            series = frame[column.name]
            if column.required and series.isna().any():
                problems.append(f"{table.name}.{column.name} has nulls but is never null")
            if column.values:
                unknown = sorted(set(series.dropna()) - set(column.values))
                if unknown:
                    problems.append(f"{table.name}.{column.name} has unlisted values {unknown}")
            if column.type == "string" and series.dropna().eq("").any():
                problems.append(f"{table.name}.{column.name} has empty strings")
    return problems


def check_keys(tables: dict[str, pd.DataFrame], codebook: Codebook) -> list[str]:
    problems = []
    for table in codebook.tables:
        frame = tables[table.name]
        key = frame[table.primary_key]
        if key.isna().any() or key.duplicated().any():
            problems.append(f"{table.name}.{table.primary_key} is not a unique key")
        for fk in table.foreign_keys:
            target = codebook.table(fk.table).primary_key
            values = set(frame[fk.field].dropna())
            missing = values - set(tables[fk.table][target])
            if missing:
                problems.append(
                    f"{table.name}.{fk.field} has {len(missing)} values not in {fk.table}, "
                    f"such as {sorted(missing)[0]}"
                )
    return problems


def check_repeated_labels(tables: dict[str, pd.DataFrame]) -> list[str]:
    """Labels repeated in candidacies agree with the tables they are repeated from."""

    problems = []
    cand = tables["candidacies"]
    for other, key in (("contests", "contest_id"), ("elections", "event_id")):
        source = tables[other].set_index(key)
        shared = [c for c in cand.columns if c in source.columns and c != key]
        renamed = source[shared].add_suffix("_source")
        joined = cand[[key, *shared]].join(renamed, on=key)
        for column in shared:
            a, b = joined[column], joined[f"{column}_source"]
            differ = ~((a == b).fillna(False) | (a.isna() & b.isna()))
            if differ.any():
                problems.append(f"candidacies.{column} differs from {other} in {differ.sum()} rows")
    return problems


def check_row_counts(tables: dict[str, pd.DataFrame], build: dict[str, pd.DataFrame]) -> list[str]:
    people = build["people"]
    expected = {
        "elections": len(build["election_events"]),
        "contests": len(build["contests"]),
        "candidacies": len(build["election_results"]),
        "people": int(people.identity_status.eq("active").sum()),
        "person_id_redirects": int(people.identity_status.eq("deprecated").sum()),
        "office_tenures": len(build["office_tenures"]),
        "parties": len(build["parties"]),
        "districts": len(build["electoral_districts"]),
    }
    return [
        f"{name} has {len(tables[name])} rows; the build has {count}"
        for name, count in expected.items()
        if len(tables[name]) != count
    ]


def check_no_contact_details(paths: list[Path]) -> list[str]:
    problems = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for what, pattern in CONTACT_PATTERNS.items():
            match = pattern.search(text)
            if match:
                problems.append(f"{path.name} holds what looks like {what}: {match.group(0)!r}")
    return problems


def check_datapackage(package_dir: Path, codebook: Codebook) -> list[str]:
    """datapackage.json lists every data file with the right checksum, size and schema."""

    problems = []
    descriptor = json.loads((package_dir / "datapackage.json").read_text(encoding="utf-8"))
    resources = {r["name"]: r for r in descriptor["resources"]}
    listed = set()
    for table in codebook.tables:
        resource = resources.get(table.name)
        if resource is None:
            problems.append(f"datapackage.json has no resource for {table.name}")
            continue
        if resource["schema"] != table_schema(table):
            problems.append(f"datapackage.json's schema for {table.name} differs from the codebook")
        header = (package_dir / resource["path"]).open(encoding="utf-8").readline()
        if header.strip().replace('"', "").split(",") != [c.name for c in table.columns]:
            problems.append(f"{resource['path']} has a header that differs from the codebook")
        entries = [resource, *resource.get("formats", {}).values()]
        if len(entries) != 4:
            problems.append(f"datapackage.json does not list four files for {table.name}")
        for entry in entries:
            listed.add(entry["path"])
    if "district_shapes" in resources:
        listed.add(resources["district_shapes"]["path"])
    else:
        problems.append("datapackage.json has no resource for the district shapes")
    for resource in descriptor["resources"]:
        for entry in [resource, *resource.get("formats", {}).values()]:
            path = package_dir / entry["path"]
            if not path.is_file():
                problems.append(f"{entry['path']} is listed but missing")
            elif entry["hash"] != "sha256:" + _sha256(path):
                problems.append(f"{entry['path']} does not match its checksum")
            elif entry["bytes"] != path.stat().st_size:
                problems.append(f"{entry['path']} does not match its size")
    present = {str(p.relative_to(package_dir)) for p in (package_dir / "data").iterdir()}
    for extra in sorted(present - listed):
        problems.append(f"{extra} is not listed in datapackage.json")
    return problems


def check_audited_links(manifest: dict, audited_sha256: str) -> list[str]:
    """The link audit's figures apply only to the links file it audited."""

    for record in manifest["artifacts"]:
        if record["local_path"] == "data/out/candidacy_person_links.csv":
            if record["sha256"] == audited_sha256:
                return []
            return [
                "candidacy_person_links.csv differs from the file the link audit covered; audit "
                "the changed links before quoting the audit's figures"
            ]
    return ["the build manifest does not list candidacy_person_links.csv"]


def run_checks(
    package_dir: Path,
    codebook: Codebook,
    tables: dict[str, pd.DataFrame],
    build: dict[str, pd.DataFrame],
    manifest: dict,
    audited_links_sha256: str | None,
) -> None:
    problems = []
    problems += check_row_counts(tables, build)
    problems += check_values(tables, codebook)
    problems += check_keys(tables, codebook)
    problems += check_repeated_labels(tables)
    problems += check_datapackage(package_dir, codebook)
    problems += check_formats_agree(package_dir, codebook)
    problems += check_checksums_csv(package_dir)
    texts = [p for p in package_dir.rglob("*") if p.suffix in {".csv", ".md", ".json", ".cff"}]
    problems += check_no_contact_details(texts)
    if audited_links_sha256:
        problems += check_audited_links(manifest, audited_links_sha256)
    if problems:
        raise CheckError(problems)
