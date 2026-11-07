# toronto-elections

Load the Toronto Election Results dataset in Python. The package downloads a published version
from Zenodo, checks every file against its published SHA-256, keeps a copy in a local cache, and
returns its tables as pandas DataFrames with typed columns and the codebook's descriptions.

```sh
pip install toronto-elections          # or: pip install "toronto-elections[geo]" for the shapes
```

```python
import torontoelections as te

te.versions()  # published versions, with dates and DOIs
candidacies = te.candidacies(version="results-2026-11-30.1")
candidacies.attrs["descriptions"]["vote_share"]  # the codebook's description of a column
```

Pass `version` to every call to pin the data your analysis uses. Without it the package uses the
newest version and prints one line saying which. The first load in a session prints the citation
of the version loaded; `te.cite()` gives it again, with BibTeX.

| Function | Returns |
|---|---|
| `versions()` | published versions, dates, DOIs and the build each came from |
| `download(version)` | downloads and checks a version; returns the folder of its files |
| `candidacies(version, source_confirmed_only=False, bodies=None, offices=None, years=None)` | one row per candidate in one Contest |
| `contests(version)`, `elections(version)`, `parties(version)` | those tables |
| `people(version)` | People, with their House of Commons, Assembly, Wikidata and ParlInfo IDs |
| `person_id_redirects(version)` | retired Person IDs and the IDs that replaced them |
| `resolve_person_id(ids, version)` | the current Person ID for each ID, retired or current |
| `office_tenures(version)` | evidence of offices held |
| `districts(version, geometry=False)` | districts; a GeoDataFrame with `geometry=True` (needs the `geo` extra) |
| `careers(person_id, version)` | each run of the given People, in date order |
| `codebook(table, version)` | the codebook of one table |
| `cite(version)` | the citation and BibTeX of a version |
| `cache_dir()`, `clear_cache(version=None)` | where the cache is, and emptying it |

`version` can also be the path of a package ZIP or folder you already have, for working without a
connection to Zenodo. The cache is in your user cache folder unless `TORONTO_ELECTIONS_CACHE`
names another.

With `source_confirmed_only=True`, `candidacies` sets `person_id` to null where the link to the
Person rests only on the build's structural rules (`person_link_basis = structural`), so a result
can be checked without those links.

The code is released under the MIT License. The data are licensed under CC BY 4.0 by their
authors; cite the version you use.
