# Provenance supplement

Toronto Election Results, version `${version}`

This supplement is for readers who want to check how the data were made. The data themselves are
in the user package, `toronto-election-records-${version}.zip`.

| File | What it holds |
|---|---|
| `candidacy_person_links.csv` | Every link between a Candidacy and a Person, with its review state, method, evidence, reviewer and the releases it is valid for. |
| `person_external_ids.csv` | Each external ID of a Person, with the basis of the match, a URL to check it and the date it was retrieved. |
| `lineage/` | The columns that record how a value was built, moved out of the user tables and keyed by each table's ID. |
| `build_manifest.json` | The build's manifest: every output file and source file with its SHA-256, and the coverage window. |
| `verification/` | The link audit, the external reconciliation, the identity reviews and their files. |
| `provenance.md` | The sources of the data and the tools and people that made it. |
| `build-notes.md` | How the build reads each source and joins identities. |
| `adr/` | The build's design decisions. |
| `CONTEXT.md` | The build's glossary of terms. |
| `toronto-election-results-${version}.zip` | The build repository at commit `${build_commit_short}`, as `git archive` writes it: the code and reference files that made this version. |

The research notes the build kept while it was made stay in the build repository,
${build_url}, and in its software archive on Zenodo.
