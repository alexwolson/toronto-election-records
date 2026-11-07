"""Compare the tables the Stata loader exported with the Python loader's, value by value.

Run after stata/tests/test_torontoelections.do, from the repository root:
    uv run --project python python stata/tests/compare_exports.py

Stata exports booleans as 0 and 1, dates as YYYY-MM-DD, and nulls as empty fields. The Python
loader's tables are checked to match by the cross-language test, so a match here is a match
with R too.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parents[2]
OUT = ROOT / "stata" / "tests" / "out"
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


def _python_text(value, dtype) -> str:
    if pd.isna(value):
        return ""
    if pd.api.types.is_bool_dtype(dtype):
        return "1" if value else "0"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _same(stata: str, python: str, dtype) -> bool:
    if pd.api.types.is_float_dtype(dtype) and stata and python:
        return math.isclose(float(stata), float(python), rel_tol=1e-9)
    if pd.api.types.is_integer_dtype(dtype) and stata and python:
        return float(stata) == float(python)
    return stata == python


def main() -> int:
    os.environ["TORONTO_ELECTIONS_REGISTRY"] = str(ROOT / "fixtures" / "versions.csv")
    os.environ["TORONTO_ELECTIONS_CACHE"] = tempfile.mkdtemp(prefix="te-compare-")
    import torontoelections as te

    version = te.versions().version.iloc[0]
    problems = []
    for table in TABLES:
        python = getattr(te, table)(version=version)
        stata = pd.read_csv(OUT / f"{table}.csv", dtype=str, keep_default_na=False)
        if stata.columns.tolist() != python.columns.tolist():
            problems.append(f"{table}: the variables differ")
            continue
        if len(stata) != len(python):
            problems.append(f"{table}: {len(stata)} rows in Stata, {len(python)} in Python")
            continue
        for column in python.columns:
            dtype = python[column].dtype
            ours = [_python_text(v, dtype) for v in python[column]]
            bad = sum(not _same(s, p, dtype) for s, p in zip(stata[column], ours, strict=True))
            if bad:
                problems.append(f"{table}.{column}: {bad} values differ")
        print(f"{table}: {len(python)} rows compared")
    for problem in problems:
        print(f"MISMATCH {problem}")
    print("Stata and Python agree." if not problems else f"{len(problems)} mismatches.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
