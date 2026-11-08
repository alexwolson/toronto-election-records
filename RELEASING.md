# Releasing a version

A version is published from one tagged build of toronto-election-results. The steps below run
from this repository after the build is frozen. Publishing on Zenodo cannot be undone, so the
commands stop at a draft and the maintainer publishes it.

## 1. Freeze the build

In toronto-election-results, follow `docs/release.md` to the tag: set the release ID and the
citation, rebuild twice and check that the tables are reproduced byte for byte, re-audit any
changed Person link, merge, and tag `results-YYYY-MM-DD.N`.

## 2. Pin the tag

In `build.toml`, set `tag` to the new tag and `commit` to the commit it points at. If the link
audit was redone, update `audited_links_sha256`. Then:

```sh
cd packaging
uv run te-package build
```

The build stops if the tag does not point at the commit, a file does not match the build manifest,
or any package check fails. Read the README, KNOWN_ISSUES and VALIDATION it writes, and update the
templates in `docs/package/` where the figures or the text no longer hold. Add the version's
entry to `docs/package/CHANGELOG.md`.

## 3. Try the draft on Zenodo Sandbox

With a token from sandbox.zenodo.org in `ZENODO_SANDBOX_TOKEN`:

```sh
uv run te-package publish --sandbox                 # the first version
uv run te-package publish --sandbox --previous ID   # a later version: ID of the latest one
```

Open the draft it prints and check the files and metadata. A Sandbox DOI starts with 10.5072.

## 4. Make the real draft and publish it

With a token from zenodo.org in `ZENODO_TOKEN`, run the same command without `--sandbox`. The
command reserves the DOI, builds the package with that DOI in its README and citation, and uploads
both ZIPs. Review the draft on Zenodo, then press Publish there.

## 5. Register the version

```sh
uv run te-package register --record RECORD_ID
```

This adds the version's row to `versions.csv`, with the package's URL, size, SHA-256 and POSIX
cksum read from the published record. Open a pull request with the change; once it is merged, the
loaders find the version.

## 6. Check it with the loaders

Load the new version with the R and Python loaders. If the package schema changed, release the
loaders first (step 8).

## 7. Deposit in Dataverse

With a checkout of the build at the tagged commit that holds the City's raw files in `data/raw/`:

```sh
uv run te-package dataverse --build-root PATH --doi 10.5281/zenodo.RECORD_ID
```

This writes `dist/dataverse-VERSION/`: both ZIPs, the City of Toronto's raw files (checked
against the build manifest, without any file that holds contact details) and `DATAVERSE.md` with
the values for the deposit form. Upload it to the CJPS Dataverse.

## 8. Release the loaders, when needed

A data version needs a loader release only when its package schema changes.

- Python: bump the version in `python/pyproject.toml` and `_package.py`, then
  `uv build && uv publish` from `python/`.
- R: bump `r/DESCRIPTION` and `loader_version` in `r/R/package.R`, add the maintainer's email to
  `Authors@R`, run `R CMD check --as-cran` and submit to CRAN.
- Stata: see `stata/README.md` on its testing status before any SSC submission.

## 9. Point to the version

Put the version DOI in the paper, the build repository's README and CITATION.cff, and announce
the version. After the first data record exists, turn off the Zenodo GitHub integration on
toronto-election-results; its existing records stay as they are.
