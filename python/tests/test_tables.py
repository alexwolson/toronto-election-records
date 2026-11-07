"""The tables: columns as the package's schema says, typed, with the codebook attached."""

from __future__ import annotations

import json
import zipfile

import pandas as pd
import pytest
from conftest import PACKAGE, VERSION

import torontoelections as te

TABLES = {
    "candidacies": te.candidacies,
    "contests": te.contests,
    "elections": te.elections,
    "people": te.people,
    "person_id_redirects": te.person_id_redirects,
    "office_tenures": te.office_tenures,
    "parties": te.parties,
    "districts": te.districts,
}
DTYPES = {
    "string": pd.StringDtype(),
    "integer": pd.Int64Dtype(),
    "number": pd.Float64Dtype(),
    "boolean": pd.BooleanDtype(),
}


def _schema():
    with zipfile.ZipFile(PACKAGE) as archive:
        name = next(n for n in archive.namelist() if n.endswith("datapackage.json"))
        descriptor = json.loads(archive.read(name))
    return {r["name"]: r["schema"]["fields"] for r in descriptor["resources"] if "schema" in r}


@pytest.mark.parametrize("name", TABLES)
def test_each_table_has_the_schema_columns_and_types(name):
    frame = TABLES[name](version=VERSION)
    fields = _schema()[name]
    assert frame.columns.tolist() == [f["name"] for f in fields]
    for field in fields:
        dtype = frame[field["name"]].dtype
        if field["type"] == "date":
            assert pd.api.types.is_datetime64_any_dtype(dtype), field["name"]
        else:
            assert dtype == DTYPES[field["type"]], (field["name"], dtype)
    assert frame.attrs["descriptions"] == {f["name"]: f["description"] for f in fields}
    assert frame.attrs["version"] == VERSION


def test_source_confirmed_only_drops_structural_links():
    full = te.candidacies(version=VERSION)
    confirmed = te.candidacies(version=VERSION, source_confirmed_only=True)
    structural = full.person_link_basis.eq("structural").fillna(False)
    assert structural.any()
    assert confirmed.loc[structural, "person_id"].isna().all()
    assert confirmed.loc[~structural, "person_id"].equals(full.loc[~structural, "person_id"])


def test_candidacies_can_be_filtered():
    full = te.candidacies(version=VERSION)
    office = full.office_type.iloc[0]
    year = int(full.election_year.iloc[0])
    body = full.represented_body.iloc[0]
    some = te.candidacies(version=VERSION, offices=[office], years=[year], bodies=[body])
    assert len(some) > 0
    assert set(some.office_type) == {office}
    assert set(some.election_year) == {year}
    assert set(some.represented_body) == {body}


def test_resolve_person_id_follows_redirects():
    redirects = te.person_id_redirects(version=VERSION)
    retired, current = redirects.iloc[0]
    active = te.people(version=VERSION).person_id.iloc[0]
    resolved = te.resolve_person_id([retired, active, "per_unknown"], version=VERSION)
    assert resolved.iloc[0] == current
    assert resolved.iloc[1] == active
    assert pd.isna(resolved.iloc[2])


def test_careers_lists_each_run_in_date_order():
    full = te.candidacies(version=VERSION)
    person = full.person_id.value_counts().index[0]
    career = te.careers(person, version=VERSION)
    assert len(career) == int(full.person_id.eq(person).sum())
    assert career.election_date.is_monotonic_increasing
    assert {"office_type", "district_name", "party_name", "votes", "elected", "incumbent"} <= set(
        career.columns
    )


def test_careers_accepts_a_retired_id():
    retired, current = te.person_id_redirects(version=VERSION).iloc[0]
    assert te.careers(retired, version=VERSION).equals(te.careers(current, version=VERSION))


def test_districts_with_geometry():
    geopandas = pytest.importorskip("geopandas")
    shapes = te.districts(version=VERSION, geometry=True)
    assert isinstance(shapes, geopandas.GeoDataFrame)
    assert shapes.crs.to_epsg() == 4326
    has_shape = shapes.geometry_status.eq("available")
    assert shapes.geometry[has_shape].notna().all()
    assert shapes.geometry[~has_shape].isna().all()


def test_codebook_describes_each_column():
    book = te.codebook("candidacies", version=VERSION)
    assert book.column.tolist() == [f["name"] for f in _schema()["candidacies"]]
    assert {"type", "label", "description", "values", "null_meaning"} <= set(book.columns)


def test_cite_gives_the_citation_and_bibtex():
    text = te.cite(version=VERSION)
    assert f"Toronto Election Results (Version {VERSION})" in text
    assert "@dataset{" in text
    assert "Olson, Alex and Elliott, Matt" in text
