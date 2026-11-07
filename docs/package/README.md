# Toronto Election Results

Version `${version}`

Toronto Election Results records the candidates and results of elections held within the City of
Toronto from ${first_year} to ${last_year}. It covers the City's Mayor and Council, the trustees of
the four school boards, and the members of Parliament and of the Ontario Legislature elected in the
City's ridings. Before the City's amalgamation in 1998 it covers the 1994 municipal elections of
the six former municipalities and Metropolitan Toronto, the 1993 federal election and the 1995
Ontario election. A person's runs for office are joined under one Person ID where evidence shows
they are the same person, so a career can be followed across offices and years.

## What the package holds

| Table | One row per | Rows |
|---|---|---:|
| `candidacies` | candidate in one Contest | ${rows_candidacies} |
| `contests` | race for one or more seats | ${rows_contests} |
| `elections` | general election or by-election | ${rows_elections} |
| `people` | Person | ${rows_people} |
| `person_id_redirects` | retired Person ID | ${rows_person_id_redirects} |
| `office_tenures` | piece of evidence that a Person held an office | ${rows_office_tenures} |
| `parties` | registered party | ${rows_parties} |
| `districts` | ward, riding or trustee area | ${rows_districts} |

Each table is in `data/` in four formats with the same rows and columns: CSV, Parquet, Stata
(`.dta`) and R (`.rds`). `data/districts.gpkg` holds the shapes of the ${n_with_shape} districts
that have one. `CODEBOOK.md`, also as `CODEBOOK.pdf`, describes every column, its units and what a
null means. `datapackage.json` lists every data file with its SHA-256 checksum and every column
with its type.

## Quick start

In R and Python, the loaders download a version, check every file against its checksum and keep a
copy for later sessions.

```r
# R
install.packages("torontoelections")
candidacies <- torontoelections::te_candidacies(version = "${version}")
```

```python
# Python: pip install toronto-elections
import torontoelections as te
candidacies = te.candidacies(version="${version}")
```

The files in this package can also be read directly:

```r
candidacies <- readRDS("data/candidacies.rds")
```

```python
import pandas as pd
candidacies = pd.read_parquet("data/candidacies.parquet")
```

In Stata (14 or later), unzip the package and open a table's `.dta` file from the package's
folder. Its variables carry the codebook's labels, and booleans are 0 and 1 with the value labels
`false` and `true`.

```stata
use "data/candidacies.dta", clear
```

To check a file, run Stata's `checksum` on it and compare the checksum and size it prints with the
`cksum` and `bytes` columns of the file's row in `checksums.csv`. They are the same POSIX CRC.

```stata
checksum "data/candidacies.dta"
```

## Before you analyse

- `person_id` is null for ${n_unlinked} Candidacies, where the evidence does not establish who
  ran. The other ${n_linked} have a Person.
- ${n_structural} Candidacies are joined to their Person under the build's structural rules, with
  no source about the person. `person_link_basis` marks them as `structural`. Repeating an
  analysis without them shows whether a result depends on them.
- `incumbent` is null where the release holds no roster that can settle it: Mayor and Council in
  1994 and 1997, and every trustee race before 2026.
- Turnout is null for every trustee race, for municipal races from 1994 to 2001 and for the 2026
  municipal election.
- Districts in different boundary sets (`boundary_regime`) cover different areas and cannot be
  compared directly.
- The build's Endorsement tables are held back from this release. Their coverage is too thin to
  support analysis, and an absent endorsement in them does not mean there was none.

`KNOWN_ISSUES.md` lists every documented limitation. `VALIDATION.md` summarizes how the data were
checked. `DATASHEET.md` answers the questions of Datasheets for Datasets. `CHANGELOG.md` records
what changed in each version.

## Versions and identifiers

The version name is the tag of the build it was made from. File names inside the package stay the
same from version to version. `candidacy_id`, `contest_id`, `event_id`, `district_id` and
`person_id` stay the same across versions. When two Persons turn out to be one, the retired ID is
listed in `person_id_redirects` with the ID that replaced it.

This version was made from commit `${build_commit_short}` of the build repository,
${build_url}. The code and records behind every value are in the provenance supplement,
`toronto-election-records-${version}-provenance.zip`.

## Citing

Olson, A., & Elliott, M. (${year}). *Toronto Election Results* (Version ${version}) [Data set].
${doi_line}

`CITATION.cff` gives the same citation in machine-readable form.

## Licence

The data and documentation are licensed under the Creative Commons Attribution 4.0 International
Licence (CC BY 4.0). The records they are built from remain subject to their publishers' terms;
`LICENSE` gives the notices those terms require.
