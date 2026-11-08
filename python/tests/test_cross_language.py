"""The R and Python loaders return the same tables: rows, columns, types and values.

R loads the fixture version with the R package in ../r, writes each table to Parquet and each
column's R class to JSON, and the test compares them with the Python loader's tables. It is
skipped where R, pkgload or the R package's dependencies are not installed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
from conftest import FIXTURES, REGISTRY, VERSION

import torontoelections as te

R_PACKAGE = Path(__file__).parents[2] / "r"
TABLES = [
    "candidacies",
    "contests",
    "elections",
    "people",
    "person_id_redirects",
    "office_tenures",
    "parties",
    "districts",
]
R_CLASS = {
    "string": "character",
    "integer": "integer",
    "number": "numeric",
    "boolean": "logical",
    "date": "Date",
}
DUMP = r"""
args <- commandArgs(trailingOnly = TRUE)
pkgload::load_all(args[[1]], quiet = TRUE)
out <- args[[2]]
classes <- list()
for (table in strsplit(args[[3]], ",")[[1]]) {
  frame <- get(paste0("te_", table))(version = args[[4]])
  classes[[table]] <- lapply(frame, function(x) class(x)[[1]])
  nanoparquet::write_parquet(frame, file.path(out, paste0(table, ".parquet")))
}
writeLines(jsonlite::toJSON(classes, auto_unbox = TRUE), file.path(out, "classes.json"))
"""


def _r_ready() -> bool:
    if shutil.which("Rscript") is None:
        return False
    probe = (
        "for (p in c('pkgload', 'nanoparquet', 'jsonlite', 'digest')) "
        "if (!requireNamespace(p, quietly = TRUE)) quit(status = 1)"
    )
    return subprocess.run(["Rscript", "-e", probe], capture_output=True).returncode == 0


@pytest.mark.skipif(not _r_ready(), reason="R with pkgload and the R package's dependencies")
def test_r_and_python_return_the_same_tables(tmp_path, monkeypatch):
    script = tmp_path / "dump.R"
    script.write_text(DUMP, encoding="utf-8")
    env = {
        "TORONTO_ELECTIONS_REGISTRY": str(REGISTRY),
        "TORONTO_ELECTIONS_CACHE": str(tmp_path / "r-cache"),
    }
    subprocess.run(
        ["Rscript", str(script), str(R_PACKAGE), str(tmp_path), ",".join(TABLES), VERSION],
        check=True,
        capture_output=True,
        env={**os.environ, **env},
    )
    r_classes = json.loads((tmp_path / "classes.json").read_text(encoding="utf-8"))
    schema = _schemas()
    for table in TABLES:
        py = getattr(te, table)(version=VERSION)
        r = pq.read_table(tmp_path / f"{table}.parquet").to_pydict()
        assert list(r) == py.columns.tolist(), table
        for field in schema[table]:
            name = field["name"]
            assert r_classes[table][name] == R_CLASS[field["type"]], (table, name)
            ours = [None if pd.isna(v) else v for v in py[name].tolist()]
            if field["type"] == "date":
                ours = [None if v is None else v.date() for v in ours]
            theirs = r[name]
            assert len(ours) == len(theirs), (table, name)
            assert ours == theirs, (table, name)


def _schemas() -> dict[str, list[dict]]:
    import zipfile

    with zipfile.ZipFile(FIXTURES / f"toronto-election-records-{VERSION}.zip") as archive:
        name = next(n for n in archive.namelist() if n.endswith("datapackage.json"))
        descriptor = json.loads(archive.read(name))
    return {r["name"]: r["schema"]["fields"] for r in descriptor["resources"] if "schema" in r}
