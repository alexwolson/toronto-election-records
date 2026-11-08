# toronto-election-records

This repository makes the user package of the Toronto Election Results dataset from one pinned
build of [toronto-election-results](https://github.com/alexwolson/toronto-election-results), checks
it and publishes it. It will also hold the R, Python and Stata loaders. It never edits data: a
change to the data goes through the build repository and a new build tag.

## What it makes

For a version, two ZIP files:

- `toronto-election-records-<version>.zip`, the user package: eight tables, each as CSV, Parquet,
  Stata and R files; the district shapes as a GeoPackage; the codebook as Markdown and PDF;
  `datapackage.json`; and the README, changelog, known issues, validation summary, datasheet,
  citation and licence.
- `toronto-election-records-<version>-provenance.zip`, the provenance supplement: the full Person
  link table, the columns moved out of the user tables, the build manifest, the verification
  reports, the build's design notes and the build repository at the pinned commit.

The version is the build's tag, such as `results-2026-11-30.1`. A build pinned without a tag makes
a development package named `dev-<commit>`, which cannot be published.

## Layout

| Path | What it holds |
|---|---|
| `build.toml` | The pinned build (repository, commit, tag) and the SHA-256 of the links file the link audit covered. |
| `codebook/codebook.yaml` | Every table and column of the package. The single source for `CODEBOOK.md` and its PDF, the schemas in `datapackage.json`, the Stata variable labels and the R `label` attributes. |
| `docs/package/` | The templates of the package's documents. Figures in them are filled from the data when the package is made. |
| `packaging/` | The Python project that makes and checks the package (`te-package`). |

## Making a package

Needs [uv](https://docs.astral.sh/uv/), git, R with the `nanoparquet` and `jsonlite` packages,
pandoc and typst.

```sh
cd packaging
uv run te-package build    # writes both ZIP files to ../dist/
uv run pytest              # tests against a small sample build in tests/fixtures/
```

The build fetches the pinned commit, checks every output file against the build manifest, makes the
tables, writes them in all four formats and runs the package checks. It stops on any failure:

- a file that does not match the manifest, or a tag that does not point at the pinned commit;
- a column the build adds or drops that the codebook does not account for;
- a moved column that the package could not recover from what it ships;
- a Person without a current confirmed link;
- a mismatch between formats, a broken key, an unlisted value or a null where the codebook says
  never;
- a links file other than the one the link audit covered, for a release;
- anything in a text file that looks like an email address, a phone number, a postal code or a
  street address.

To change what a table ships, edit `codebook/codebook.yaml` and the table's entry in
`packaging/src/te_package/tables.py`. `packaging/tests/fixtures/make_fixture.py` regenerates the
test sample from a build.

## Licence

The code is released under the MIT License. The codebook and the package documents are licensed
under CC BY 4.0, like the data. See [LICENSE](LICENSE).
