"""Cut a small, self-consistent build from a real build of toronto-election-results.

The tests run against this sample so they need no network. It keeps a few Candidacies of each
kind the package handles (each link basis, a Candidacy without a Person, an Acclamation, a
partial Contest, an incumbent with a held district, a Party candidate, a 2026 candidate with a
website) and every row those Candidacies reach through keys. It writes the build's Parquet tables
and a manifest whose checksums cover the files written.

Usage:
    uv run python tests/fixtures/make_fixture.py BUILD_ROOT OUT_ROOT
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

TABLES = (
    "election_results",
    "contests",
    "election_events",
    "people",
    "candidacy_person_links",
    "person_external_ids",
    "office_tenures",
    "parties",
    "electoral_districts",
    "endorsers",
    "endorsement_assertions",
    "endorsements",
    "endorsement_coverage",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pick_candidacies(er, links, people) -> list[str]:
    rows = er.to_pandas()
    cur = links.to_pandas()
    cur = cur[cur.valid_to_release.isna() & cur.link_status.eq("confirmed")]
    picked: list[str] = []

    def take(frame, n=1):
        picked.extend(frame.candidacy_id.head(n).tolist())

    for basis in ("own_record", "official_record", "person_specific_source", "structural"):
        ids = cur[cur.evidence_basis.eq(basis)].candidacy_id
        take(rows[rows.candidacy_id.isin(ids)], 2)
    take(rows[rows.person_id.isna()], 2)
    take(rows[rows.outcome_method.eq("acclamation")])
    take(rows[rows.coverage_status.eq("partial") & rows.elected.isna()])
    take(rows[rows.incumbent_held_district_id.notna()])
    take(rows[rows.affiliation_status.eq("party")])
    take(rows[rows.campaign_url.notna()])
    take(rows[rows.incumbent_appointed.eq(True)])
    take(rows[rows.office_type.eq("mpp") & rows.election_year.eq(1999)])
    # The Person a merge retired: keep the run that now carries its replacement.
    retired = people.to_pandas().query("identity_status == 'deprecated'")
    take(rows[rows.person_id.isin(retired.redirect_to_person_id)])
    # Every other Candidacy in the picked Contests, so the Contests stay whole.
    contests = rows[rows.candidacy_id.isin(picked)].contest_id.unique()
    return rows[rows.contest_id.isin(contests)].candidacy_id.tolist()


def main(build_root: Path, out_root: Path) -> None:
    src = build_root / "data" / "out"
    t = {name: pq.read_table(src / f"{name}.parquet") for name in TABLES}
    keep = {}
    cand = _pick_candidacies(t["election_results"], t["candidacy_person_links"], t["people"])
    er = t["election_results"].filter(
        pc.is_in(t["election_results"]["candidacy_id"], pa.array(cand))
    )
    keep["election_results"] = er
    contests = set(er["contest_id"].to_pylist())
    void = t["contests"].filter(pc.equal(t["contests"]["outcome_method"], "void"))
    contests.add(void["contest_id"][0].as_py())
    keep["contests"] = t["contests"].filter(
        pc.is_in(t["contests"]["contest_id"], pa.array(sorted(contests)))
    )
    events = set(keep["contests"]["event_id"].to_pylist())
    keep["election_events"] = t["election_events"].filter(
        pc.is_in(t["election_events"]["event_id"], pa.array(sorted(events)))
    )
    keep["candidacy_person_links"] = t["candidacy_person_links"].filter(
        pc.is_in(t["candidacy_person_links"]["candidacy_id"], pa.array(cand))
    )
    persons = {p for p in er["person_id"].to_pylist() if p}
    retired = t["people"].filter(pc.equal(t["people"]["identity_status"], "deprecated"))
    persons |= set(retired["person_id"].to_pylist())
    tenures = t["office_tenures"].filter(
        pc.is_in(t["office_tenures"]["person_id"], pa.array(sorted(persons)))
    )
    keep["office_tenures"] = tenures
    keep["people"] = t["people"].filter(
        pc.is_in(t["people"]["person_id"], pa.array(sorted(persons)))
    )
    keep["person_external_ids"] = t["person_external_ids"].filter(
        pc.is_in(t["person_external_ids"]["person_id"], pa.array(sorted(persons)))
    )
    parties = {p for p in er["party_id"].to_pylist() if p}
    keep["parties"] = t["parties"].filter(
        pc.is_in(t["parties"]["party_id"], pa.array(sorted(parties)))
    )
    districts = set(keep["contests"]["district_id"].to_pylist())
    districts |= {d for d in er["incumbent_held_district_id"].to_pylist() if d}
    districts |= {d for d in tenures["district_id"].to_pylist() if d}
    keep["electoral_districts"] = t["electoral_districts"].filter(
        pc.is_in(t["electoral_districts"]["district_id"], pa.array(sorted(districts)))
    )
    for name in ("endorsers", "endorsement_assertions", "endorsements", "endorsement_coverage"):
        keep[name] = t[name].slice(0, 2)

    out = out_root / "data" / "out"
    out.mkdir(parents=True, exist_ok=True)
    artifacts = []
    written = []
    for name in TABLES:
        path = out / f"{name}.parquet"
        pq.write_table(keep[name], path)
        written.append((name, path))
        # The supplement copies these two tables' CSV files from the build.
        if name in ("candidacy_person_links", "person_external_ids"):
            csv_path = out / f"{name}.csv"
            pacsv.write_csv(keep[name], csv_path)
            written.append((name, csv_path))
        print(f"{name}: {keep[name].num_rows} rows")
    for name, path in written:
        artifacts.append(
            {
                "bytes": path.stat().st_size,
                "local_path": f"data/out/{path.name}",
                "rows": keep[name].num_rows,
                "sha256": _sha256(path),
            }
        )
    real = json.loads((src / "build_manifest.json").read_text(encoding="utf-8"))
    manifest = {
        "artifacts": artifacts,
        "generated_at": real["generated_at"],
        "schema_version": real["schema_version"],
        "sources": real["sources"][:2],
    }
    (out / "build_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
