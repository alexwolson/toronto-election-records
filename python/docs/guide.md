# A worked guide to toronto-elections

This guide loads one version of Toronto Election Results and walks through six uses of it. Replace
`VERSION` with the version you cite; `te.versions()` lists them.

```python
import torontoelections as te

VERSION = "results-2026-11-30.1"
```

## 1. Load the candidacies of a pinned version

```python
candidacies = te.candidacies(version=VERSION)
candidacies.shape
candidacies.attrs["descriptions"]["incumbent"]
```

Each row is one candidate in one Contest. Columns are typed: counts are nullable integers, flags
nullable booleans and dates datetimes. A null means what the codebook says it means;
`te.codebook("candidacies", version=VERSION)` lists every column.

## 2. Incumbents' win rates by office

```python
incumbents = candidacies[candidacies["incumbent"].eq(True) & candidacies["elected"].notna()]
incumbents.groupby("office_type")["elected"].mean()
```

`incumbent` is null where the release holds no roster that settles it, so keep only rows where it
is true rather than treating null as false.

## 3. One person's career across levels of government

```python
people = te.people(version=VERSION)
person = people.loc[people["preferred_name"].eq("Olivia Chow"), "person_id"].iloc[0]
te.careers(person, version=VERSION)[
    ["election_date", "office_type", "district_name", "party_name", "votes", "elected"]
]
```

`careers` accepts a retired Person ID too, and follows it to the Person that replaced it.

## 4. Join People to Wikidata and ParlInfo

```python
members = people.dropna(subset=["wikidata_id"])
members[["person_id", "preferred_name", "wikidata_id", "parlinfo_id"]].head()
```

Only People who sat in the House of Commons or the Legislative Assembly of Ontario have these IDs.

## 5. Check that a result does not rest on structural links

```python
confirmed = te.candidacies(version=VERSION, source_confirmed_only=True)
for frame in (candidacies, confirmed):
    runs = frame.dropna(subset=["person_id"]).groupby("person_id").size()
    print((runs > 1).sum(), "People with more than one run")
```

With `source_confirmed_only=True`, a Candidacy whose link rests only on the build's structural
rules has no Person. Repeating an analysis this way shows how much it depends on those links.

## 6. Map the 2022 council results

```python
shapes = te.districts(version=VERSION, geometry=True)  # needs the geo extra
council_2022 = candidacies[
    candidacies["office_type"].eq("councillor") & candidacies["election_year"].eq(2022)
]
winners = council_2022[council_2022["elected"].eq(True)]
winners_map = shapes.merge(winners[["district_id", "vote_share"]], on="district_id")
winners_map.plot(column="vote_share", legend=True)
```

Districts in different boundary sets cover different areas, so map one election, or one boundary
set, at a time.
