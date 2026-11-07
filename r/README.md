# torontoelections

Load the Toronto Election Results dataset in R. The package downloads a published version from
Zenodo, checks every file against its published SHA-256, keeps a copy in a local cache, and
returns its tables as data frames with R types and the codebook's labels.

```r
install.packages("torontoelections")
library(torontoelections)

te_versions()                                   # published versions, with dates and DOIs
candidacies <- te_candidacies(version = "results-2026-11-30.1")
attr(candidacies$vote_share, "description")     # the codebook's description of a column
```

Pass `version` to every call to pin the data your analysis uses. Without it the package uses the
newest version and says which. The first load in a session prints the citation of the version
loaded; `te_cite()` gives it again, with BibTeX, and `citation("torontoelections")` cites the
dataset and the package.

| Function | Returns |
|---|---|
| `te_versions()` | published versions, dates, DOIs and the build each came from |
| `te_download(version)` | downloads and checks a version; returns the folder of its files |
| `te_candidacies(version, source_confirmed_only = FALSE, bodies, offices, years)` | one row per candidate in one Contest |
| `te_contests(version)`, `te_elections(version)`, `te_parties(version)` | those tables |
| `te_people(version)` | People, with their House of Commons, Assembly, Wikidata and ParlInfo IDs |
| `te_person_id_redirects(version)` | retired Person IDs and the IDs that replaced them |
| `te_resolve_person_id(ids, version)` | the current Person ID for each ID, retired or current |
| `te_office_tenures(version)` | evidence of offices held |
| `te_districts(version, geometry = FALSE)` | districts; an `sf` object with `geometry = TRUE` (needs sf) |
| `te_careers(person_id, version)` | each run of the given People, in date order |
| `te_codebook(table, version)` | the codebook of one table |
| `te_cite(version)` | the citation and BibTeX of a version |
| `te_cache_dir()`, `te_clear_cache(version)` | where the cache is, and emptying it |

`version` can also be the path of a package ZIP or folder you already have, for working without a
connection to Zenodo. The cache is in the folder `tools::R_user_dir("torontoelections", "cache")`
gives, unless `TORONTO_ELECTIONS_CACHE` names another. `vignette("torontoelections")` is a worked
guide.

The code is released under the MIT License. The data are licensed under CC BY 4.0 by their
authors; cite the version you use.
