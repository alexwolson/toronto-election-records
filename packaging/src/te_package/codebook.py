"""Read the codebook and render it as Markdown, Frictionless table schemas and Arrow schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CODEBOOK_PATH = REPO_ROOT / "codebook" / "codebook.yaml"

TYPES = {
    "string": pa.string(),
    "integer": pa.int64(),
    "number": pa.float64(),
    "boolean": pa.bool_(),
    "date": pa.date32(),
}


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    label: str
    description: str
    null: str
    values: tuple[str, ...] = ()
    units: str | None = None

    @property
    def required(self) -> bool:
        return self.null == "never"


@dataclass(frozen=True)
class ForeignKey:
    field: str
    table: str


@dataclass(frozen=True)
class Table:
    name: str
    title: str
    grain: str
    description: str
    primary_key: str
    columns: tuple[Column, ...]
    foreign_keys: tuple[ForeignKey, ...] = ()

    def column(self, name: str) -> Column:
        return next(c for c in self.columns if c.name == name)


@dataclass(frozen=True)
class Codebook:
    schema_version: str
    tables: tuple[Table, ...] = field(default_factory=tuple)

    def table(self, name: str) -> Table:
        return next(t for t in self.tables if t.name == name)


def load_codebook(path: Path = CODEBOOK_PATH) -> Codebook:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    tables = []
    for t in raw["tables"]:
        columns = tuple(
            Column(
                name=c["name"],
                type=c["type"],
                label=c["label"],
                description=" ".join(str(c["description"]).split()),
                null=" ".join(str(c["null_when"]).split()),
                values=tuple(c.get("values", ())),
                units=c.get("units"),
            )
            for c in t["columns"]
        )
        keys = tuple(ForeignKey(k["field"], k["table"]) for k in t.get("foreign_keys", ()))
        tables.append(
            Table(
                name=t["name"],
                title=t["title"],
                grain=t["grain"],
                description=" ".join(t["description"].split()),
                primary_key=t["primary_key"],
                columns=columns,
                foreign_keys=keys,
            )
        )
    return Codebook(schema_version=raw["schema_version"], tables=tuple(tables))


def arrow_schema(table: Table) -> pa.Schema:
    return pa.schema(
        [pa.field(c.name, TYPES[c.type], nullable=not c.required) for c in table.columns]
    )


def table_schema(table: Table) -> dict:
    """The Frictionless Table Schema of one table."""

    fields = []
    for c in table.columns:
        entry = {"name": c.name, "type": c.type, "title": c.label, "description": c.description}
        constraints = {}
        if c.required:
            constraints["required"] = True
        if c.values:
            constraints["enum"] = list(c.values)
        if constraints:
            entry["constraints"] = constraints
        if c.type == "boolean":
            entry["trueValues"] = ["true"]
            entry["falseValues"] = ["false"]
        entry["null_meaning"] = "Never null." if c.required else c.null
        if c.units:
            entry["units"] = c.units
        fields.append(entry)
    return {
        "fields": fields,
        "missingValues": [""],
        "primaryKey": [table.primary_key],
        "foreignKeys": [
            {"fields": [k.field], "reference": {"resource": k.table, "fields": [k.field]}}
            for k in table.foreign_keys
        ],
    }


def _column_entry(column: Column) -> str:
    null = "never null" if column.required else "can be null"
    lines = [f"- **`{column.name}`** ({column.type}, {null}). {column.description}"]
    if column.units:
        lines.append(f"  Units: {column.units}.")
    if column.values:
        lines.append("  Values: " + ", ".join(f"`{v}`" for v in column.values) + ".")
    if not column.required:
        lines.append(f"  {column.null}")
    return "  \n".join(lines)


def render_markdown(codebook: Codebook, version: str) -> str:
    """CODEBOOK.md: every table and column, with type, units, allowed values and null meaning."""

    parts = [
        "# Codebook",
        "",
        f"Toronto Election Results, version `{version}`. Package schema {codebook.schema_version}.",
        "",
        "Each table comes in four files with the same rows and columns: CSV (UTF-8, an empty "
        "field is a null), Parquet, Stata (`.dta`) and R (`.rds`). In the Stata files a boolean "
        "is stored as 0 or 1 with the value labels `false` and `true`, and a null string is "
        "empty. Dates are polling days and other calendar dates, written as `YYYY-MM-DD` in the "
        "CSV files.",
        "",
        "| Table | One row per | Key |",
        "|---|---|---|",
    ]
    for table in codebook.tables:
        grain = table.grain.removeprefix("One row per ").rstrip(".")
        parts.append(f"| `{table.name}` | {grain} | `{table.primary_key}` |")
    for table in codebook.tables:
        parts += [
            "",
            f"## `{table.name}`",
            "",
            f"{table.title}. {table.grain} {table.description}",
            "",
        ]
        parts.append(f"Key: `{table.primary_key}`.")
        if table.foreign_keys:
            joins = ", ".join(f"`{k.field}` to `{k.table}`" for k in table.foreign_keys)
            parts.append(f"Joins: {joins}.")
        parts.append("")
        parts += [_column_entry(c) for c in table.columns]
    return "\n".join(parts) + "\n"
