# Changelog

## ${version}

The first version published as a user package. Earlier releases of the build are archived on
Zenodo as copies of the build repository.

- The tables are renamed for users: `election_results` is `candidacies`, `election_events` is
  `elections` and `electoral_districts` is `districts`. District shapes are in
  `data/districts.gpkg`.
- `candidacies` gains `person_link_basis`, from the link table, and `source_url`, the published
  URL of each source record. `contests` and `office_tenures` gain `source_url`, and `districts`
  gains `geometry_source_url`.
- `people` holds the active People only, with their House of Commons, Legislative Assembly of
  Ontario, Wikidata and ParlInfo IDs as columns. Retired Person IDs are in the new table
  `person_id_redirects`.
- Columns that record how a value was built are moved to the provenance supplement, keyed by
  each table's ID: from `candidacies`, `party_name_raw`, `party_jurisdiction`,
  `incumbent_office_tenure_id`, `predecessor_office_tenure_id`, `incumbent_reported`,
  `result_status`, `source_resource`, `source_detail` and `source_candidacy_id`; from `contests`,
  `result_status`, `source_resource` and `source_detail`; from `office_tenures`, `source_detail`;
  from `people`, `created_release`; from `districts`, `geometry_source_detail`, `geometry_crs`,
  `geometry_derivation` and the three `geometry_membership_source_*` columns. The full link table
  and the external ID table are in the supplement too.
- The build's Endorsement tables are held back from this release.
- Retired IDs: ${rows_person_id_redirects} Person ID, listed in `person_id_redirects`.
