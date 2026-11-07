from __future__ import annotations

from te_package.codebook import TYPES, load_codebook, render_markdown, table_schema

CODEBOOK = load_codebook()


def test_names_and_labels_fit_stata():
    for table in CODEBOOK.tables:
        for column in table.columns:
            assert len(column.name) <= 32, column.name
            assert len(column.label) <= 80, column.name
            assert column.type in TYPES, column.name


def test_keys_are_columns_of_their_tables():
    names = {t.name for t in CODEBOOK.tables}
    for table in CODEBOOK.tables:
        columns = {c.name for c in table.columns}
        assert table.primary_key in columns
        for key in table.foreign_keys:
            assert key.field in columns
            assert key.table in names


def test_markdown_names_every_table_and_column():
    text = render_markdown(CODEBOOK, version="dev-0000000")
    for table in CODEBOOK.tables:
        assert f"## `{table.name}`" in text
        for column in table.columns:
            assert f"`{column.name}`" in text


def test_table_schema_follows_the_codebook():
    table = CODEBOOK.table("candidacies")
    schema = table_schema(table)
    assert [f["name"] for f in schema["fields"]] == [c.name for c in table.columns]
    assert schema["primaryKey"] == ["candidacy_id"]
    assert {
        "fields": ["contest_id"],
        "reference": {"resource": "contests", "fields": ["contest_id"]},
    } in schema["foreignKeys"]
    office = next(f for f in schema["fields"] if f["name"] == "office_type")
    assert office["constraints"] == {
        "required": True,
        "enum": ["mayor", "councillor", "trustee", "mp", "mpp"],
    }
    person = next(f for f in schema["fields"] if f["name"] == "person_id")
    assert "required" not in person.get("constraints", {})
    assert schema["missingValues"] == [""]
