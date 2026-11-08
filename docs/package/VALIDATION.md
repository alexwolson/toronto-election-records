# Validation

Version `${version}`

The data were checked in three ways: by the build's release gates, by an audit of the links that
join a person's runs, and by a comparison with two datasets compiled independently. The full
reports, with the files behind them, are in the provenance supplement under `verification/`.

## Release gates

The build refuses to write a release that fails any of its gates. Among them, it rejects:

- an election date outside the coverage window;
- a broken key, a duplicate ID, or a label repeated in a row that differs from the table it comes
  from;
- negative votes, totals or shares that do not add up, and turnout counts at different scopes;
- a decided Contest without exactly as many winners as seats, except where candidates tie across
  the last seat;
- an Acclamation with more candidates than seats, or with votes;
- a Person link or an incumbency that no evidence supports;
- a shape that is invalid or far outside the City;
- the same candidate name in two trustee wards of one board at one election, which would mean
  votes were filed under the wrong Contest.

Each source adapter also checks its own list of events and districts and its row counts against
the official archives.

The package is checked again when it is made from the build:

- every input file matches the SHA-256 in the build's manifest;
- each table has the build's row count, and the columns the codebook lists, in its order;
- the CSV, Parquet, Stata and R files of each table hold the same values;
- keys are unique, every key that refers to another table is found there, and the labels repeated
  in `candidacies` agree with `contests` and `elections`;
- every value of a column with listed values is one of them, and no column that is never null has
  a null;
- `datapackage.json` matches the files and the codebook;
- no file holds an email address, a phone number, a postal code or a street address.

## Person links

A join is two consecutive runs of one Person. The release has 2,614 joins across all Persons.
They were audited in two stages. In November 2026 a stratified random sample of the joins was
checked by AI agents that had not made or reviewed any link and did not read the release's
repository. Each looked for sources on its own, under fixed rules, and rated each join confirmed,
contradicted or not confirmed. A join was confirmed only when a source named both runs, or gave a
distinctive fact for one run that another source gave for the other. A second agent then checked
every confirmation against the cited pages. The 136 joins made after that sample were checked as a
census, under the same rules.

No join was found to tie two different people. Weighting the sample by the size of each stratum,
the share of false joins is 0.0%, with a one-sided 95% upper bound of 3.7%. The share of joins
confirmed from sources the auditors found themselves is 71.4% (95% interval 63.0% to 77.3%). The
rest could be neither confirmed nor refuted from open sources.

These figures cover the links file whose SHA-256 is `${audited_links_sha256}`. The package build
checks that this version's `candidacy_person_links.csv`, in the provenance supplement, is that
file.

A coding of a sample of the same joins by people, with access to newspaper archives, is under way.
Its results will be added to `verification/` when it is complete.

## External reconciliation

The results were compared with Semra Sevi's files of federal and Ontario candidates (Harvard
Dataverse, doi:10.7910/DVN/ABFNSQ, version 9) and the Canadian Municipal Elections Database
(Borealis, doi:10.5683/SP2/4MZJPQ, version 6). The comparison was run on the build at commit
`84b52d2`. Of the 749 Contests compared, 681 agree on every candidate's name and vote total and on
the winners. Each difference in the other 68 was checked against the election authority's own
results, and none is an error in the release. The differences are errors in the external files,
names spelled or ordered differently, two by-elections that Sevi's Ontario file lacks, and three
choices the release documents: the final recount of one 1994 race, null vote totals for
Acclamations, and no Candidacy for a candidate whose votes were not counted.
