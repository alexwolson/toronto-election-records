tables <- list(
  candidacies = te_candidacies,
  contests = te_contests,
  elections = te_elections,
  people = te_people,
  person_id_redirects = te_person_id_redirects,
  office_tenures = te_office_tenures,
  parties = te_parties,
  districts = te_districts
)
classes <- c(string = "character", integer = "integer", number = "numeric", boolean = "logical", date = "Date")

test_that("each table has the schema's columns, R types and labels", {
  local_fixture()
  for (name in names(tables)) {
    frame <- tables[[name]](version = fixture_version())
    fields <- schema_fields(name)
    expect_identical(class(frame), "data.frame")
    expect_equal(names(frame), vapply(fields, function(f) f$name, ""), info = name)
    for (field in fields) {
      column <- frame[[field$name]]
      expect_equal(class(column)[[1]], classes[[field$type]], info = paste(name, field$name))
      expect_equal(attr(column, "label"), field$title, info = paste(name, field$name))
      expect_equal(attr(column, "description"), field$description, info = paste(name, field$name))
    }
    expect_equal(attr(frame, "version"), fixture_version())
  }
})

test_that("source_confirmed_only drops structural links", {
  local_fixture()
  full <- te_candidacies(version = fixture_version())
  confirmed <- te_candidacies(version = fixture_version(), source_confirmed_only = TRUE)
  structural <- full$person_link_basis %in% "structural"
  expect_true(any(structural))
  expect_true(all(is.na(confirmed$person_id[structural])))
  expect_equal(confirmed$person_id[!structural], full$person_id[!structural])
})

test_that("te_candidacies can be filtered", {
  local_fixture()
  full <- te_candidacies(version = fixture_version())
  some <- te_candidacies(
    version = fixture_version(),
    bodies = full$represented_body[[1]],
    offices = full$office_type[[1]],
    years = full$election_year[[1]]
  )
  expect_gt(nrow(some), 0)
  expect_equal(unique(some$office_type), full$office_type[[1]])
  expect_equal(unique(some$election_year), full$election_year[[1]])
  expect_equal(unique(some$represented_body), full$represented_body[[1]])
})

test_that("te_resolve_person_id follows redirects", {
  local_fixture()
  redirects <- te_person_id_redirects(version = fixture_version())
  active <- te_people(version = fixture_version())$person_id[[1]]
  resolved <- te_resolve_person_id(
    c(redirects$retired_person_id[[1]], active, "per_unknown"),
    version = fixture_version()
  )
  expect_equal(resolved[[1]], redirects$person_id[[1]])
  expect_equal(resolved[[2]], active)
  expect_true(is.na(resolved[[3]]))
})

test_that("te_careers lists each run in date order and accepts a retired ID", {
  local_fixture()
  full <- te_candidacies(version = fixture_version())
  counts <- sort(table(full$person_id), decreasing = TRUE)
  person <- names(counts)[[1]]
  career <- te_careers(person, version = fixture_version())
  expect_equal(nrow(career), as.integer(counts[[1]]))
  expect_false(is.unsorted(career$election_date))
  expect_true(all(c("office_type", "district_name", "party_name", "votes", "elected", "incumbent") %in% names(career)))
  redirects <- te_person_id_redirects(version = fixture_version())
  expect_equal(
    te_careers(redirects$retired_person_id[[1]], version = fixture_version()),
    te_careers(redirects$person_id[[1]], version = fixture_version())
  )
})

test_that("te_districts can return shapes", {
  testthat::skip_if_not_installed("sf")
  local_fixture()
  shapes <- te_districts(version = fixture_version(), geometry = TRUE)
  expect_s3_class(shapes, "sf")
  expect_equal(sf::st_crs(shapes)$epsg, 4326L)
  has_shape <- shapes$geometry_status == "available"
  expect_true(all(!sf::st_is_empty(shapes[has_shape, ])))
  expect_true(all(sf::st_is_empty(shapes[!has_shape, ])))
})

test_that("te_codebook describes each column", {
  local_fixture()
  book <- te_codebook("candidacies", version = fixture_version())
  expect_equal(book$column, vapply(schema_fields("candidacies"), function(f) f$name, ""))
  expect_true(all(c("type", "label", "description", "values", "null_meaning") %in% names(book)))
})

test_that("te_cite gives the citation and BibTeX", {
  local_fixture()
  text <- te_cite(version = fixture_version())
  expect_match(text, paste0("Toronto Election Results (Version ", fixture_version(), ")"), fixed = TRUE)
  expect_match(text, "@dataset{", fixed = TRUE)
  expect_match(text, "Olson, Alex and Elliott, Matt", fixed = TRUE)
})
