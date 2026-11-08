# Datasheet

Version `${version}`

These are answers to the questions of *Datasheets for Datasets* (Gebru et al.).

## Motivation

**Why was the dataset made?** To give researchers and journalists one consistent record of every
election held within the City of Toronto since the last elections before amalgamation, with each
person's runs joined across offices and years. The official results are scattered across the City,
Elections Canada, Elections Ontario and archived web pages, in formats that change from one
election to the next, and none of them joins a person's runs.

**Who made it?** Alex Olson (University of Toronto) and Matt Elliott.

## Composition

**What does a row represent?** Each table's row is described in `CODEBOOK.md`. The main table,
`candidacies`, has one row per candidate in one Contest.

**How many rows are there?** ${rows_candidacies} Candidacies in ${rows_contests} Contests at
${rows_elections} Election events, with ${rows_people} People.

**Is it a sample?** No. It holds every Contest within the City for the offices covered, from the
first election in scope for each level (federal 1993, municipal 1994, Ontario 1995) to ${last_year}.
Municipal by-elections from 1995 to 1997 may be incomplete; `KNOWN_ISSUES.md` explains why.

**Is anything missing?** Some votes in ${n_partial} partial Contests, turnout for trustees and for
early municipal races, incumbency where no roster survives, and shapes for some districts.
`KNOWN_ISSUES.md` lists each gap.

**Are there links between rows?** Yes. `person_id` joins a person's Candidacies. Every other ID
joins a row to its Contest, Election event, district or Party. `CODEBOOK.md` lists the keys.

**Are there errors or noise?** The link audit bounds the share of false joins (see
`VALIDATION.md`). Errors found in the sources are corrected and documented in `KNOWN_ISSUES.md`.

**Is it self-contained?** Yes. The provenance supplement holds the build's code and the records
behind every value. The source files themselves stay with their publishers and are cited by URL.

**Does it hold confidential data?** No. Every value comes from a public record. Candidates' contact
details and residences, which some source files carry, are left out, and the package build checks
that no file holds an email address, a phone number, a postal code or a street address.

**Does it identify people?** Yes. Candidates for public office are named, as the election
authorities publish them.

## Collection

**How were the data collected?** From the official results of the City of Toronto, Elections
Canada and Elections Ontario, the City's archived results pages, the Toronto Star's printed results
where the official record does not survive, the House of Commons and the Legislative Assembly of
Ontario for members' terms, and City Council records for municipal incumbency. The provenance
supplement's `provenance.md` names each source and how it was used.

**Over what period?** The elections run from 1993 to ${last_year}. The data were gathered in 2026.

**How were people's runs joined?** A run is joined to an earlier one only on evidence: an official
record that ties the two, a source about the person, or the build's structural rules where no such
source was found. Similar names alone never make a join. `person_link_basis` records which applies.

## Preprocessing

Names are put given name first, Parties are matched to one identity per registered party, and
districts are keyed to the boundary set they were drawn in. The source records, including the
names as printed, are kept in the release or the provenance supplement.

## Uses

**What is it for?** The study of elections and political careers in Toronto: incumbency, turnover,
candidate supply, the movement of politicians between levels of government, and comparisons over
time within one boundary set.

**What should it not be used for?** Comparing districts across boundary sets as if they covered the
same area. Treating a null `incumbent` as false. Treating the Persons without a link as new
candidates. Inferring anything about a person beyond their public candidacies and offices.

## Distribution

The package is published on Zenodo, with a DOI for each version, under the Creative Commons
Attribution 4.0 International Licence. It is also deposited in the Canadian Journal of Political
Science Dataverse.

## Maintenance

Alex Olson maintains the dataset. Errors can be reported as issues at
https://github.com/alexwolson/toronto-election-records. Each new version gets its own DOI under one
concept DOI, earlier versions stay available, and `CHANGELOG.md` records what changed, including
any retired ID. Errors found after a version is published are listed in that version's errata in
`KNOWN_ISSUES.md` and fixed in the next.
