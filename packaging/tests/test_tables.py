from __future__ import annotations

import json

import pandas as pd
import pytest

from te_package.codebook import load_codebook
from te_package.tables import (
    BUILD_TABLES,
    BuildDataError,
    make_tables,
    resolve_redirects,
    source_urls,
    tenure_source_urls,
)

CODEBOOK = load_codebook()


def test_source_urls_drops_the_detail_after_the_url():
    assert source_urls("https://a.ca/x.zip :: 2003/ward1.xls") == "https://a.ca/x.zip"
    assert source_urls("https://a.ca/p#part;https://b.ca/q") == "https://a.ca/p;https://b.ca/q"
    assert (
        source_urls("https://m.ca/1993results.zip#canelr93/tcand.txt,canelr93/ersraw.txt")
        == "https://m.ca/1993results.zip"
    )


def test_source_urls_keeps_each_url_once_in_order():
    detail = "https://a.ca/x.zip :: f1;https://b.ca/y;https://a.ca/x.zip :: f2"
    assert source_urls(detail) == "https://a.ca/x.zip;https://b.ca/y"


def test_tenure_source_urls_finds_every_url_in_the_evidence():
    detail = json.dumps(
        {
            "source_url": "https://a.ca/roster.csv",
            "evidence_urls": ["https://b.ca/bio", "https://a.ca/roster.csv"],
            "rule": "last roster",
            "nested": {"page": "https://c.ca/p#section"},
        }
    )
    assert tenure_source_urls(detail) == "https://a.ca/roster.csv;https://b.ca/bio;https://c.ca/p"
    assert tenure_source_urls("https://a.ca/1;https://a.ca/2") == "https://a.ca/1;https://a.ca/2"
    assert tenure_source_urls(json.dumps({"rule": "x", "source_files": ["data/raw/a.csv"]})) is None


def test_every_user_table_has_the_codebook_columns_in_order(build_tables):
    made = make_tables(build_tables)
    assert list(made.tables) == [t.name for t in CODEBOOK.tables]
    for table in CODEBOOK.tables:
        assert list(made.tables[table.name].columns) == [c.name for c in table.columns]


def test_person_link_basis_comes_from_the_current_confirmed_link(build_tables):
    candidacies = make_tables(build_tables).tables["candidacies"]
    links = build_tables["candidacy_person_links"]
    current = links[links.link_status.eq("confirmed") & links.valid_to_release.isna()]
    expected = current.set_index("candidacy_id").evidence_basis
    linked = candidacies[candidacies.person_id.notna()]
    assert linked.person_link_basis.tolist() == expected.loc[linked.candidacy_id].tolist()
    assert candidacies[candidacies.person_id.isna()].person_link_basis.isna().all()
    assert set(linked.person_link_basis) == {
        "own_record",
        "official_record",
        "person_specific_source",
        "structural",
    }


def test_a_person_without_a_confirmed_link_stops_the_build(build_tables):
    links = build_tables["candidacy_person_links"]
    linked = build_tables["election_results"].dropna(subset=["person_id"]).candidacy_id.iloc[0]
    build_tables["candidacy_person_links"] = links[links.candidacy_id.ne(linked)]
    with pytest.raises(BuildDataError, match=linked):
        make_tables(build_tables)


def test_a_result_that_is_not_final_stops_the_build(build_tables):
    er = build_tables["election_results"]
    er.loc[er.index[0], "result_status"] = "pending"
    with pytest.raises(BuildDataError, match="result_status"):
        make_tables(build_tables)


def test_a_party_jurisdiction_the_package_cannot_recover_stops_the_build(build_tables):
    er = build_tables["election_results"]
    er.loc[er.index[0], "party_jurisdiction"] = "somewhere_else"
    with pytest.raises(BuildDataError, match="party_jurisdiction"):
        make_tables(build_tables)


@pytest.mark.parametrize("table", ["election_results", "contests", "electoral_districts"])
def test_a_new_build_column_stops_the_build(build_tables, table):
    build_tables[table]["brand_new_column"] = "x"
    with pytest.raises(BuildDataError, match="brand_new_column"):
        make_tables(build_tables)


def test_a_missing_build_column_stops_the_build(build_tables):
    build_tables["election_results"] = build_tables["election_results"].drop(columns="votes")
    with pytest.raises(BuildDataError, match="votes"):
        make_tables(build_tables)


def test_people_holds_active_people_with_their_external_ids(build_tables):
    people = make_tables(build_tables).tables["people"]
    registry = build_tables["people"]
    assert set(people.person_id) == set(registry[registry.identity_status.eq("active")].person_id)
    ids = build_tables["person_external_ids"]
    for row in ids.itertuples():
        assert (
            people.set_index("person_id").at[row.person_id, f"{row.scheme}_id"] == row.external_id
        )


def test_redirects_point_retired_ids_at_active_people(build_tables):
    redirects = make_tables(build_tables).tables["person_id_redirects"]
    registry = build_tables["people"]
    retired = registry[registry.identity_status.eq("deprecated")]
    assert set(redirects.retired_person_id) == set(retired.person_id)
    assert redirects.person_id.isin(registry[registry.identity_status.eq("active")].person_id).all()


def test_resolve_redirects_follows_a_chain():
    people = pd.DataFrame(
        {
            "person_id": ["a", "b", "c"],
            "identity_status": ["deprecated", "deprecated", "active"],
            "redirect_to_person_id": ["b", "c", None],
        }
    )
    assert resolve_redirects(people) == {"a": "c", "b": "c"}


def test_moved_columns_go_to_the_lineage_tables(build_tables):
    made = make_tables(build_tables)
    lineage = made.lineage["candidacies"]
    assert list(lineage.columns) == [
        "candidacy_id",
        "party_name_raw",
        "party_jurisdiction",
        "incumbent_office_tenure_id",
        "predecessor_office_tenure_id",
        "incumbent_reported",
        "result_status",
        "source_resource",
        "source_detail",
        "source_candidacy_id",
    ]
    assert len(lineage) == len(build_tables["election_results"])
    assert list(made.lineage["contests"].columns) == [
        "contest_id",
        "result_status",
        "source_resource",
        "source_detail",
    ]


def test_district_shapes_hold_only_districts_with_a_shape(build_tables):
    made = make_tables(build_tables)
    districts = made.tables["districts"]
    assert "geometry" not in districts.columns
    available = districts[districts.geometry_status.eq("available")]
    assert len(available) > 0
    assert sorted(made.shapes.district_id) == sorted(available.district_id)
    assert made.shapes.crs.to_epsg() == 4326


def test_endorsement_tables_are_never_read():
    assert not any(name.startswith("endorse") for name in BUILD_TABLES)
