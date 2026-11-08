"""Turn the build's tables into the user package's tables.

Each user table is declared by the build table it comes from, the columns made here, the columns
moved to the provenance supplement and the columns used but not shipped. The build's columns must
be exactly those the declaration accounts for, so a column the build adds or drops stops the
package until the codebook says what to do with it. Two moved columns can only be moved because
the package can recover them, and the build stops if that stops being true.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import shapely

from te_package.codebook import Codebook, Table, arrow_schema, load_codebook

BUILD_TABLES = (
    "election_results",
    "contests",
    "election_events",
    "people",
    "candidacy_person_links",
    "person_external_ids",
    "office_tenures",
    "parties",
    "electoral_districts",
)

LINK_COLUMNS = (
    "candidacy_id",
    "person_id",
    "link_status",
    "method",
    "evidence",
    "reviewer",
    "valid_from_release",
    "valid_to_release",
    "evidence_basis",
)
EXTERNAL_ID_COLUMNS = ("person_id", "scheme", "external_id", "basis", "source_url", "retrieved_on")
EXTERNAL_ID_SCHEMES = ("house_of_commons", "ontario_legislature", "wikidata", "parlinfo")


class BuildDataError(Exception):
    """The build's tables are not what the package expects."""


@dataclass(frozen=True)
class Spec:
    source: str
    key: str
    made: tuple[str, ...] = ()
    moved: tuple[str, ...] = ()
    unused: tuple[str, ...] = ()


SPECS = {
    "elections": Spec("election_events", "event_id"),
    "contests": Spec(
        "contests",
        "contest_id",
        made=("source_url",),
        moved=("result_status", "source_resource", "source_detail"),
    ),
    "candidacies": Spec(
        "election_results",
        "candidacy_id",
        made=("person_link_basis", "source_url"),
        moved=(
            "party_name_raw",
            "party_jurisdiction",
            "incumbent_office_tenure_id",
            "predecessor_office_tenure_id",
            "incumbent_reported",
            "result_status",
            "source_resource",
            "source_detail",
            "source_candidacy_id",
        ),
    ),
    "people": Spec(
        "people",
        "person_id",
        made=tuple(f"{s}_id" for s in EXTERNAL_ID_SCHEMES),
        moved=("created_release",),
        unused=("identity_status", "redirect_to_person_id"),
    ),
    "office_tenures": Spec(
        "office_tenures", "office_tenure_id", made=("source_url",), moved=("source_detail",)
    ),
    "parties": Spec("parties", "party_id"),
    "districts": Spec(
        "electoral_districts",
        "district_id",
        made=("geometry_source_url",),
        moved=(
            "geometry_source_detail",
            "geometry_crs",
            "geometry_derivation",
            "geometry_membership_source_authority",
            "geometry_membership_source_resource",
            "geometry_membership_source_date",
        ),
        unused=("geometry",),
    ),
}


@dataclass
class UserTables:
    tables: dict[str, pd.DataFrame]
    lineage: dict[str, pd.DataFrame]
    shapes: gpd.GeoDataFrame
    links: pd.DataFrame
    external_ids: pd.DataFrame


def read_build(out: Path) -> dict[str, pd.DataFrame]:
    """Read the build tables the package uses. The endorsement tables are never read."""

    return {
        name: pq.read_table(out / f"{name}.parquet").to_pandas(types_mapper=pd.ArrowDtype)
        for name in BUILD_TABLES
    }


def source_urls(detail: str) -> str:
    """The published URLs in a `source_detail`, without the detail the build adds after them."""

    urls: list[str] = []
    for part in detail.split(";"):
        url = part.split(" :: ")[0].split("#")[0].strip()
        if url and url not in urls:
            urls.append(url)
    return ";".join(urls)


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def tenure_source_urls(detail: str) -> str | None:
    """Every published URL in an Office tenure's evidence, which is JSON or a list of URLs."""

    texts = _strings(json.loads(detail)) if detail.lstrip().startswith("{") else [detail]
    found = [source_urls(t) for t in texts if t.startswith(("http://", "https://"))]
    joined = source_urls(";".join(found))
    return joined or None


def _check_columns(build: dict[str, pd.DataFrame], codebook: Codebook) -> None:
    problems = []
    expected: dict[str, set[str]] = {
        "candidacy_person_links": set(LINK_COLUMNS),
        "person_external_ids": set(EXTERNAL_ID_COLUMNS),
    }
    for name, spec in SPECS.items():
        shipped = {c.name for c in codebook.table(name).columns}
        expected[spec.source] = (shipped - set(spec.made)) | set(spec.moved) | set(spec.unused)
    for source, columns in expected.items():
        actual = set(build[source].columns)
        for extra in sorted(actual - columns):
            problems.append(f"{source} has a column the package does not account for: {extra}")
        for missing in sorted(columns - actual):
            problems.append(f"{source} lacks a column the package expects: {missing}")
    if problems:
        raise BuildDataError("; ".join(problems))


def _check_moves(build: dict[str, pd.DataFrame]) -> None:
    er = build["election_results"]
    for source in ("election_results", "contests"):
        status = build[source].result_status
        if not status.eq("final").all():
            raise BuildDataError(
                f"{source}.result_status is not final on every row, so it cannot move to the "
                "supplement"
            )
    parties = build["parties"].set_index("party_id").jurisdiction
    has_party = er.party_id.notna()
    expected = er.party_id.map(parties).where(has_party, er.election_authority)
    if not er.party_jurisdiction.eq(expected).all():
        raise BuildDataError(
            "party_jurisdiction differs from parties.jurisdiction or election_authority on some "
            "rows, so it cannot move to the supplement"
        )


def _conform(frame: pd.DataFrame, table: Table) -> pd.DataFrame:
    columns = [c.name for c in table.columns]
    arrow = pa.Table.from_pandas(frame[columns], preserve_index=False).cast(arrow_schema(table))
    return arrow.to_pandas(types_mapper=pd.ArrowDtype)


def _lineage(frame: pd.DataFrame, spec: Spec) -> pd.DataFrame:
    return frame[[spec.key, *spec.moved]].reset_index(drop=True)


def _candidacies(build: dict[str, pd.DataFrame]) -> pd.DataFrame:
    er = build["election_results"].copy()
    links = build["candidacy_person_links"]
    current = links[links.link_status.eq("confirmed") & links.valid_to_release.isna()]
    doubled = current.candidacy_id[current.candidacy_id.duplicated()]
    if len(doubled):
        raise BuildDataError(f"Candidacies with two confirmed links: {', '.join(doubled)}")
    basis = current.set_index("candidacy_id")[["person_id", "evidence_basis"]]
    basis = basis.rename(columns={"person_id": "person_id_link"})
    joined = er[["candidacy_id", "person_id"]].join(basis, on="candidacy_id")
    linked = joined.person_id.notna()
    unsupported = joined[linked & (joined.person_id_link.ne(joined.person_id).fillna(True))]
    if len(unsupported):
        raise BuildDataError(
            "Candidacies whose Person has no current confirmed link: "
            + ", ".join(unsupported.candidacy_id)
        )
    er["person_link_basis"] = joined.evidence_basis.where(linked)
    er["source_url"] = er.source_detail.map(source_urls)
    return er


def resolve_redirects(people: pd.DataFrame) -> dict[str, str]:
    """Map each retired Person ID to the active Person at the end of its chain of redirects."""

    status = dict(zip(people.person_id, people.identity_status, strict=True))
    target = dict(zip(people.person_id, people.redirect_to_person_id, strict=True))
    resolved = {}
    for retired in people.person_id[people.identity_status.eq("deprecated")]:
        seen = [retired]
        current = target[retired]
        while current is not None and not pd.isna(current) and status.get(current) == "deprecated":
            if current in seen:
                raise BuildDataError(f"the redirects from {retired} form a loop")
            seen.append(current)
            current = target[current]
        if current is None or pd.isna(current) or status.get(current) != "active":
            raise BuildDataError(f"the retired Person {retired} does not lead to an active Person")
        resolved[retired] = current
    return resolved


def _people(build: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    registry = build["people"]
    ids = build["person_external_ids"]
    unknown = sorted(set(ids.scheme) - set(EXTERNAL_ID_SCHEMES))
    if unknown:
        raise BuildDataError(f"person_external_ids has schemes the codebook lacks: {unknown}")
    if ids.duplicated(["person_id", "scheme"]).any():
        raise BuildDataError("person_external_ids has two IDs of one scheme for a Person")
    wide = ids.pivot(index="person_id", columns="scheme", values="external_id")
    wide = wide.reindex(columns=list(EXTERNAL_ID_SCHEMES))
    wide.columns = [f"{s}_id" for s in wide.columns]
    active = registry[registry.identity_status.eq("active")]
    people = active.join(wide, on="person_id")
    redirects = pd.DataFrame(
        list(resolve_redirects(registry).items()), columns=["retired_person_id", "person_id"]
    )
    return people, redirects


def _shapes(districts: pd.DataFrame, table: Table) -> gpd.GeoDataFrame:
    has_shape = districts.geometry.notna()
    if not has_shape.eq(districts.geometry_status.eq("available")).all():
        raise BuildDataError("geometry is present exactly where geometry_status is not available")
    crs = set(districts.geometry_crs[has_shape])
    if crs - {"EPSG:4326"}:
        raise BuildDataError(f"district shapes in an unexpected CRS: {sorted(crs)}")
    rows = districts[has_shape]
    columns = [c.name for c in table.columns]
    frame = _conform(
        rows.assign(geometry_source_url=rows.geometry_source_detail.map(source_urls)), table
    )
    geometry = shapely.from_wkb([bytes(g) for g in rows.geometry])
    return gpd.GeoDataFrame(frame[columns], geometry=geometry, crs="EPSG:4326")


def make_tables(build: dict[str, pd.DataFrame], codebook: Codebook | None = None) -> UserTables:
    codebook = codebook or load_codebook()
    _check_columns(build, codebook)
    _check_moves(build)

    frames: dict[str, pd.DataFrame] = {}
    lineage: dict[str, pd.DataFrame] = {}
    frames["elections"] = build["election_events"]
    contests = build["contests"].copy()
    contests["source_url"] = contests.source_detail.map(source_urls)
    frames["contests"] = contests
    frames["candidacies"] = _candidacies(build)
    people, redirects = _people(build)
    frames["people"] = people
    frames["person_id_redirects"] = redirects
    tenures = build["office_tenures"].copy()
    tenures["source_url"] = tenures.source_detail.map(tenure_source_urls)
    frames["office_tenures"] = tenures
    frames["parties"] = build["parties"]
    districts = build["electoral_districts"].copy()
    districts["geometry_source_url"] = districts.geometry_source_detail.map(
        source_urls, na_action="ignore"
    )
    frames["districts"] = districts

    for name, spec in SPECS.items():
        if spec.moved:
            lineage[name] = _lineage(frames[name], spec)
    tables = {t.name: _conform(frames[t.name], t) for t in codebook.tables}
    return UserTables(
        tables=tables,
        lineage=lineage,
        shapes=_shapes(build["electoral_districts"], codebook.table("districts")),
        links=build["candidacy_person_links"],
        external_ids=build["person_external_ids"],
    )
