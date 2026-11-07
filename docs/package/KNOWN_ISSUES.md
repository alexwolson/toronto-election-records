# Known issues

Version `${version}`

This file lists the documented limitations of the data and any errors found after the version
was published. A later version that fixes an error says so in `CHANGELOG.md`.

## Errata

None reported for this version.

## People and links

- ${n_unlinked} Candidacies have no Person. For each, the evidence does not establish who ran, or
  the only Person proposed was rejected. Their `incumbent` is null.
- ${n_structural} Candidacies are joined to their Person under the build's structural rules, with
  no source about the person (`person_link_basis = structural`). VALIDATION.md gives the audit's
  bound on false joins.
- ${n_people_without_candidacy} People have no Candidacy. Each was appointed to Council to fill a
  vacancy and holds an Office tenure the release needs to set incumbency.
- `preferred_name` is the name the release uses for a Person. The names in `candidacies` are kept
  as each ballot printed them, so one Person can appear under several spellings.

## Incumbency

- `incumbent` is null for Mayor and Council in 1994 and 1997. The release holds no roster of the
  councils elected before 1994, and the amalgamated Council first sat in 1998. For 1997,
  `predecessor_incumbent` records who sat on Metro Council or one of the six former councils.
- `incumbent` is null for every trustee race before 2026, because no complete roster of the
  four boards has been acquired. For 2026 it comes from the boards' own material on the 20
  sitting trustees who ran.
- The sitting members at the 1995 Ontario election are known only from Elections Ontario's
  incumbent flag. Their tenures have no start date and their `incumbent_appointed` is null.
- `incumbent_changed_district` is set across a boundary change only for the 2018 council
  election, by comparing the polls of the old and new wards. For other boundary changes it is
  null.

## Results

- ${n_partial} Contests are `partial`: their sources do not give every candidate's votes or the
  winner, so some `votes`, totals or `elected` values are null.

${partial_contests}

- ${n_acclamation} Contests were decided by Acclamation. Their votes, totals, shares and ranks are
  null.
- ${n_void} Contests were declared void. They are in `contests` and have no Candidacies.
- In a Contest with more than one seat each voter could cast several votes, so `vote_share` is a
  share of votes, not of voters. Every 1997 council ward elected two members.
- The 1994 Toronto Ward 3 race carries the final judicial recount (Mario Silva 2,979, Tony
  O'Donohue 2,969) in place of the election-night count.
- Elections Ontario's 2011 file gives Willowdale's two Brown candidates each other's totals, and
  its 2006 Parkdale—High Park by-election file codes a Libertarian candidate as Liberal. The
  release corrects both.
- Cynthia Lai, a council candidate in Ward 23 Scarborough North in 2022, died three days before
  polling. The City did not count votes cast for her, so she has no Candidacy in that Contest.
- Most 1994 and 1997 trustee Contests and eight 1994 council Contests come from the Toronto
  Star's printed results, because the City's archived pages lack them. `source_authority` says
  so on each row.
- Municipal by-elections are complete from 1998. The former municipalities left no index of
  their by-elections from 1995 to 1997. One was found, North York's Ward 1 in 1995, and it is
  included.

## Turnout

- Turnout is null for every trustee race. The City's count of electors who cast a municipal
  ballot is not a count for any board.
- For Mayor and Council, `turnout_scope = composite_municipal_ballot`: the count is of electors
  who cast a municipal ballot in the ward, shared by the Mayor and Councillor races.
- Turnout is null for municipal races from 1994 to 2001, whose archived pages give no elector
  counts, and for the 2026 municipal election until the City publishes its voter statistics.
- Turnout is null for the September 2026 Scarborough Southwest provincial by-election, whose
  official tabulation gives no elector count.

## Districts and shapes

- A district keeps one name within its boundary set. Federal district 35008 is Broadview—Greenwood
  in both 1997 and 2000, although Elections Canada ran the 2000 election under its new name,
  Toronto—Danforth.
- Conseil scolaire Viamonde's 1997 Region 1B also took in Markham, Richmond Hill, Vaughan, King and
  Whitchurch-Stouffville. Every other Contest lies within the City.
- Districts used since 1997 that have no shape in this version:

${missing_shapes}

- No district used only before 1997 has a shape: the 1994 municipal districts, the 1987 federal
  ridings and Ontario's 1987 ridings.
- Ontario's 1999 and 2007 ridings use the shapes of the federal ridings that the Representation
  Acts of 1996 and 2005 adopted. Elections Ontario's 2018 ridings match the federal 2013 ridings
  to within 1% of their area, except along the lakeshore, where the two files draw the shoreline
  and the islands differently.

## Held back from this release

- The build's Endorsement tables. They cover 160 endorsements by nine Endorsers in Mayor and
  Council races, and only a small share of the Endorser and Contest pairs were searched in full.
  They may return as a release of their own once coverage is enough.
