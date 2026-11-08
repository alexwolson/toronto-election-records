"""Fill the package's document templates with figures taken from the data."""

from __future__ import annotations

import string
from pathlib import Path

from te_package.build_input import BuildPin
from te_package.codebook import REPO_ROOT, Codebook
from te_package.tables import UserTables

TEMPLATES = REPO_ROOT / "docs" / "package"
ATTRIBUTION_START = "The release is built from"


class DocumentError(Exception):
    """A document cannot be made from its template."""


def _n(value: int) -> str:
    return f"{value:,}"


def _build_url(pin: BuildPin) -> str:
    if pin.repository.startswith("https://github.com/"):
        return f"{pin.repository.removesuffix('.git')}/tree/{pin.commit}"
    return pin.repository


def attributions(build_root: Path) -> str:
    """The build LICENSE's notice of its sources, which the package must carry."""

    text = (build_root / "LICENSE").read_text(encoding="utf-8")
    start = text.find(ATTRIBUTION_START)
    end = text.find("\n---")
    if start < 0 or end < start:
        raise DocumentError("cannot find the source notice in the build's LICENSE")
    return text[start:end].strip()


def _partial_contests(made: UserTables) -> str:
    contests = made.tables["contests"]
    elections = made.tables["elections"].set_index("event_id")
    rows = contests[contests.coverage_status.eq("partial")].join(elections, on="event_id")
    lines = [
        f"- {r.election_date}: {r.represented_body}, {r.district_name} ({r.office_type})"
        for r in rows.sort_values(["election_date", "district_name"]).itertuples()
    ]
    return "\n".join(lines) or "- None."


def _missing_shapes(made: UserTables) -> str:
    """Boundary sets with districts used since 1997 that have no shape."""

    cand = made.tables["candidacies"]
    used = set(cand[cand.election_year.ge(1997)].district_id)
    districts = made.tables["districts"]
    missing = districts[
        districts.district_id.isin(used) & districts.geometry_status.ne("available")
    ]
    counts = missing.groupby("boundary_regime").size()
    lines = [f"- `{regime}`: {n} district{'' if n == 1 else 's'}" for regime, n in counts.items()]
    return "\n".join(lines) or "- None. Every district used since 1997 has a shape."


def template_values(
    made: UserTables,
    manifest: dict,
    pin: BuildPin,
    codebook: Codebook,
    build_root: Path,
    audited_links_sha256: str | None = None,
    doi: str | None = None,
) -> dict[str, str]:
    cand = made.tables["candidacies"]
    contests = made.tables["contests"]
    districts = made.tables["districts"]
    linked = cand.person_id.notna()
    structural = cand.person_link_basis.eq("structural")
    years = made.tables["elections"].election_year
    values = {
        "version": pin.version,
        "schema_version": codebook.schema_version,
        "build_commit": pin.commit,
        "build_commit_short": pin.commit[:7],
        "build_url": _build_url(pin),
        "build_date": str(manifest["generated_at"])[:10],
        "first_year": str(int(years.min())),
        "last_year": str(int(years.max())),
        "n_linked": _n(int(linked.sum())),
        "n_unlinked": _n(int((~linked).sum())),
        "n_structural": _n(int(structural.fillna(False).sum())),
        "n_people_with_candidacy": _n(int(cand.person_id.dropna().nunique())),
        "n_partial": _n(int(contests.coverage_status.eq("partial").sum())),
        "n_void": _n(int(contests.outcome_method.eq("void").sum())),
        "n_acclamation": _n(int(contests.outcome_method.eq("acclamation").sum())),
        "n_with_shape": _n(int(districts.geometry_status.eq("available").sum())),
        "partial_contests": _partial_contests(made),
        "missing_shapes": _missing_shapes(made),
        "attributions": attributions(build_root),
        "year": str(manifest["generated_at"])[:4],
        "doi_line": f"Zenodo. https://doi.org/{doi}"
        if doi
        else "Development build, without a DOI.",
        "doi_cff": f'doi: "{doi}"\n' if doi else "",
        "audited_links_sha256": audited_links_sha256 or "(not checked in this development build)",
        "n_people_without_candidacy": _n(
            len(made.tables["people"]) - int(cand.person_id.dropna().nunique())
        ),
    }
    for name, frame in made.tables.items():
        values[f"rows_{name}"] = _n(len(frame))
    return values


def render(name: str, values: dict[str, str]) -> str:
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    try:
        return string.Template(text).substitute(values)
    except (KeyError, ValueError) as error:
        raise DocumentError(f"{name}: {error}") from error
