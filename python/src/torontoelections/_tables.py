"""Read the tables of a version as typed DataFrames with the codebook attached."""

from __future__ import annotations

import os
from collections.abc import Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from torontoelections import _package
from torontoelections._package import LoaderError

Version = str | os.PathLike | None

_TYPES = {
    pa.string(): pd.StringDtype(),
    pa.large_string(): pd.StringDtype(),
    pa.int64(): pd.Int64Dtype(),
    pa.int32(): pd.Int64Dtype(),
    pa.float64(): pd.Float64Dtype(),
    pa.bool_(): pd.BooleanDtype(),
}
CAREER_COLUMNS = [
    "person_id",
    "candidate_name",
    "election_date",
    "election_type",
    "office_type",
    "represented_body",
    "district_id",
    "district_name",
    "boundary_regime",
    "party_name",
    "affiliation_status",
    "votes",
    "vote_share",
    "vote_rank",
    "elected",
    "acclaimed",
    "incumbent",
    "candidacy_id",
    "contest_id",
]


def _fields(descriptor: dict, table: str) -> list[dict]:
    for resource in descriptor["resources"]:
        if resource["name"] == table:
            return resource["schema"]["fields"]
    raise LoaderError(f"This version has no table named {table}.")


def _read(table: str, version: Version) -> pd.DataFrame:
    root, descriptor, row = _package.resolve(version)
    _package.cite_once(descriptor, row)
    fields = _fields(descriptor, table)
    arrow = pq.read_table(root / "data" / f"{table}.parquet")
    frame = arrow.to_pandas(types_mapper=_TYPES.get, date_as_object=False)
    if frame.columns.tolist() != [f["name"] for f in fields]:
        raise LoaderError(f"{table}.parquet does not have the columns datapackage.json lists.")
    frame.attrs = {
        "table": table,
        "version": descriptor["version"],
        "labels": {f["name"]: f["title"] for f in fields},
        "descriptions": {f["name"]: f["description"] for f in fields},
    }
    return frame


def _keep_attrs(frame: pd.DataFrame, attrs: dict) -> pd.DataFrame:
    frame.attrs = dict(attrs)
    return frame


def candidacies(
    version: Version = None,
    source_confirmed_only: bool = False,
    bodies: Iterable[str] | None = None,
    offices: Iterable[str] | None = None,
    years: Iterable[int] | None = None,
) -> pd.DataFrame:
    """One row per candidate in one Contest.

    With ``source_confirmed_only``, ``person_id`` is null where the link to the Person rests only
    on the build's structural rules. ``bodies``, ``offices`` and ``years`` keep only the rows with
    those values of ``represented_body``, ``office_type`` and ``election_year``.
    """

    frame = _read("candidacies", version)
    attrs = frame.attrs
    if source_confirmed_only:
        structural = frame["person_link_basis"].eq("structural").fillna(False)
        frame.loc[structural, "person_id"] = pd.NA
    keep = pd.Series(True, index=frame.index)
    if bodies is not None:
        keep &= frame["represented_body"].isin(list(bodies))
    if offices is not None:
        keep &= frame["office_type"].isin(list(offices))
    if years is not None:
        keep &= frame["election_year"].isin([int(y) for y in years])
    if not keep.all():
        frame = frame.loc[keep].reset_index(drop=True)
    return _keep_attrs(frame, attrs)


def contests(version: Version = None) -> pd.DataFrame:
    """One row per Contest."""

    return _read("contests", version)


def elections(version: Version = None) -> pd.DataFrame:
    """One row per Election event."""

    return _read("elections", version)


def parties(version: Version = None) -> pd.DataFrame:
    """One row per Party."""

    return _read("parties", version)


def people(version: Version = None) -> pd.DataFrame:
    """One row per active Person, with their external IDs."""

    return _read("people", version)


def person_id_redirects(version: Version = None) -> pd.DataFrame:
    """Retired Person IDs and the active IDs that replaced them."""

    return _read("person_id_redirects", version)


def office_tenures(version: Version = None) -> pd.DataFrame:
    """One row per piece of evidence that a Person held an office."""

    return _read("office_tenures", version)


def districts(version: Version = None, geometry: bool = False) -> pd.DataFrame:
    """One row per district; with ``geometry``, a GeoDataFrame in EPSG:4326."""

    frame = _read("districts", version)
    if not geometry:
        return frame
    try:
        import geopandas
    except ImportError as error:
        raise LoaderError(
            'The shapes need geopandas: pip install "toronto-elections[geo]"'
        ) from error
    root = _package.resolve(version)[0]
    shapes = geopandas.read_file(root / "data" / "districts.gpkg", layer="districts")
    shapes = pd.DataFrame(
        {"district_id": shapes["district_id"].astype("string"), "geometry": shapes.geometry}
    )
    merged = frame.merge(shapes, on="district_id", how="left")
    return _keep_attrs(
        geopandas.GeoDataFrame(merged, geometry="geometry", crs="EPSG:4326"), frame.attrs
    )


def resolve_person_id(ids: str | Iterable[str], version: Version = None) -> pd.Series:
    """The current Person ID for each ID, whether retired or current; null for an unknown ID."""

    ids = [ids] if isinstance(ids, str) else list(ids)
    redirects = person_id_redirects(version)
    replaced = dict(zip(redirects["retired_person_id"], redirects["person_id"], strict=True))
    active = set(people(version)["person_id"])
    current = [replaced.get(i, i if i in active else pd.NA) for i in ids]
    return pd.Series(current, dtype="string", name="person_id")


def careers(person_id: str | Iterable[str], version: Version = None) -> pd.DataFrame:
    """Each run of the given People, in date order, with office, district, party and result."""

    current = resolve_person_id(person_id, version).dropna().unique()
    frame = candidacies(version)
    attrs = frame.attrs
    runs = frame.loc[frame["person_id"].isin(list(current)), CAREER_COLUMNS]
    runs = runs.sort_values(["person_id", "election_date", "candidacy_id"]).reset_index(drop=True)
    return _keep_attrs(runs, attrs)


def codebook(table: str, version: Version = None) -> pd.DataFrame:
    """The codebook of one table: each column's type, label, description, values and nulls."""

    _, descriptor, _ = _package.resolve(version)
    rows = []
    for field in _fields(descriptor, table):
        rows.append(
            {
                "column": field["name"],
                "type": field["type"],
                "label": field["title"],
                "description": field["description"],
                "values": ", ".join(field.get("constraints", {}).get("enum", [])),
                "null_meaning": field["null_meaning"],
                "units": field.get("units", ""),
            }
        )
    return pd.DataFrame(rows)
