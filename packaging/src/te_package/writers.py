"""Write a user table as CSV, Parquet, Stata and R files, and the shapes as a GeoPackage."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import tempfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from te_package.codebook import Table, arrow_schema

FORMATS = ("csv", "parquet", "dta", "rds")
RDS_SCRIPT = Path(__file__).with_name("rds.R")
STATA_LONG_MAX = 2_147_483_620
STATA_STR_MAX = 2045


class WriteError(Exception):
    """A table cannot be written in one of the package formats."""


def to_arrow(frame: pd.DataFrame, table: Table) -> pa.Table:
    return pa.Table.from_pandas(frame, preserve_index=False).cast(arrow_schema(table))


def write_csv(arrow: pa.Table, path: Path) -> None:
    pacsv.write_csv(arrow, path, pacsv.WriteOptions(quoting_style="needed"))


def stata_frame(arrow: pa.Table, table: Table) -> pd.DataFrame:
    """The table as Stata stores it: booleans as 0/1 with labels, integers as long."""

    frame = pd.DataFrame(index=range(arrow.num_rows))
    for column in table.columns:
        values = arrow.column(column.name)
        if column.type == "string":
            frame[column.name] = pd.array(values.to_pylist(), dtype="string")
        elif column.type == "integer":
            series = pd.array(values.to_pylist(), dtype="Int64")
            if (pd.Series(series).abs() > STATA_LONG_MAX).any():
                raise WriteError(f"{table.name}.{column.name} is too large for a Stata long")
            frame[column.name] = series.astype("Int32")
        elif column.type == "number":
            frame[column.name] = pd.array(values.to_pylist(), dtype="Float64").astype("float64")
        elif column.type == "boolean":
            labels = [None if v is None else ("true" if v else "false") for v in values.to_pylist()]
            frame[column.name] = pd.Categorical(labels, categories=["false", "true"])
        elif column.type == "date":
            frame[column.name] = pd.to_datetime(pd.Series(values.to_pylist(), dtype="object"))
    return frame


def write_dta(arrow: pa.Table, table: Table, path: Path, stamp: dt.datetime) -> None:
    frame = stata_frame(arrow, table)
    strl = [
        c.name
        for c in table.columns
        if c.type == "string" and frame[c.name].str.len().max(skipna=True) > STATA_STR_MAX
    ]
    frame.to_stata(
        path,
        write_index=False,
        version=118,
        convert_dates={c.name: "td" for c in table.columns if c.type == "date"},
        variable_labels={c.name: c.label for c in table.columns},
        data_label=f"Toronto Election Results: {table.title}"[:80],
        time_stamp=stamp,
        convert_strl=strl,
    )


def run_r(*args: str) -> None:
    result = subprocess.run(["Rscript", str(RDS_SCRIPT), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise WriteError(f"Rscript {' '.join(args[:1])} failed: {result.stderr.strip()}")


def write_rds(parquet: Path, table: Table, path: Path) -> None:
    columns = [{"name": c.name, "type": c.type, "label": c.label} for c in table.columns]
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "columns.json"
        spec.write_text(json.dumps(columns), encoding="utf-8")
        run_r("write", str(parquet), str(spec), str(path))


def write_table(
    frame: pd.DataFrame, table: Table, data_dir: Path, stamp: dt.datetime
) -> dict[str, Path]:
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = {fmt: data_dir / f"{table.name}.{fmt}" for fmt in FORMATS}
    arrow = to_arrow(frame, table)
    pq.write_table(arrow, paths["parquet"], compression="zstd")
    write_csv(arrow, paths["csv"])
    write_dta(arrow, table, paths["dta"], stamp)
    write_rds(paths["parquet"], table, paths["rds"])
    return paths


def write_shapes(shapes: gpd.GeoDataFrame, path: Path) -> None:
    frame = shapes.copy()
    for name in frame.columns:
        if name != "geometry" and isinstance(frame[name].dtype, pd.ArrowDtype):
            frame[name] = pd.Series(frame[name].tolist(), index=frame.index, dtype="object")
    frame.to_file(path, driver="GPKG", layer="districts", engine="pyogrio")
