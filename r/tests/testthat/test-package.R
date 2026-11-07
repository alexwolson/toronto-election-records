test_that("te_versions lists the registry", {
  local_fixture()
  table <- te_versions()
  expect_equal(table$version, fixture_version())
  expect_true(all(c("version", "published", "doi", "build_commit") %in% names(table)))
})

test_that("te_download checks a version and caches it", {
  cache <- local_fixture()
  folder <- te_download(fixture_version())
  expect_true(file.exists(file.path(folder, "datapackage.json")))
  expect_true(startsWith(normalizePath(folder), normalizePath(cache)))
  expect_equal(te_download(fixture_version()), folder)
})

test_that("a package that does not match its published checksum is refused", {
  local_fixture()
  copy <- withr::local_tempdir()
  file.copy(file.path(fixtures_dir(), "versions.csv"), copy)
  file.copy(fixture_zip(), copy)
  zip <- file.path(copy, basename(fixture_zip()))
  bytes <- readBin(zip, "raw", file.size(zip))
  bytes[101] <- as.raw(bitwXor(as.integer(bytes[101]), 255L))
  writeBin(bytes, zip)
  withr::local_envvar(TORONTO_ELECTIONS_REGISTRY = file.path(copy, "versions.csv"))
  expect_error(te_download(fixture_version()), "SHA-256")
})

test_that("a changed data file is refused", {
  local_fixture()
  folder <- withr::local_tempdir()
  utils::unzip(fixture_zip(), exdir = folder)
  root <- list.dirs(folder, recursive = FALSE)[[1]]
  parquet <- file.path(root, "data", "parties.parquet")
  writeBin(c(readBin(parquet, "raw", file.size(parquet)), as.raw(0)), parquet)
  expect_error(te_parties(version = root), "parties.parquet")
})

test_that("a newer package schema asks for a newer loader", {
  local_fixture()
  folder <- withr::local_tempdir()
  utils::unzip(fixture_zip(), exdir = folder)
  root <- list.dirs(folder, recursive = FALSE)[[1]]
  path <- file.path(root, "datapackage.json")
  descriptor <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  descriptor$schema_version <- "2.0.0"
  jsonlite::write_json(descriptor, path, auto_unbox = TRUE)
  expect_error(te_parties(version = root), "newer release of torontoelections")
})

test_that("a local ZIP loads without the registry", {
  local_fixture()
  withr::local_envvar(TORONTO_ELECTIONS_REGISTRY = file.path(tempdir(), "missing.csv"))
  expect_gt(nrow(te_parties(version = fixture_zip())), 0)
})

test_that("without a version the newest is used and named once", {
  local_fixture()
  messages <- testthat::capture_messages({
    te_parties()
    te_contests()
  })
  text <- paste(messages, collapse = "")
  expect_equal(lengths(regmatches(text, gregexpr(paste0("version ", fixture_version()), text))), 1)
  expect_match(text, paste0('version = "', fixture_version(), '"'), fixed = TRUE)
})

test_that("the first load prints the citation once", {
  local_fixture()
  messages <- testthat::capture_messages({
    te_parties(version = fixture_version())
    te_parties(version = fixture_version())
  })
  text <- paste(messages, collapse = "")
  expect_equal(lengths(regmatches(text, gregexpr("Toronto Election Results (Version", text, fixed = TRUE))), 1)
})

test_that("an empty registry says nothing is published", {
  local_fixture()
  empty <- withr::local_tempfile(fileext = ".csv")
  writeLines(readLines(file.path(fixtures_dir(), "versions.csv"))[[1]], empty)
  withr::local_envvar(TORONTO_ELECTIONS_REGISTRY = empty)
  expect_error(te_candidacies(), "No version")
})

test_that("an unreachable registry falls back to the cached copy", {
  local_fixture()
  te_versions()
  withr::local_envvar(TORONTO_ELECTIONS_REGISTRY = "https://example.invalid/versions.csv")
  expect_warning(table <- te_versions(), "cached copy")
  expect_equal(table$version, fixture_version())
})

test_that("an unknown version is named", {
  local_fixture()
  expect_error(te_parties(version = "results-1999-01-01.1"), "results-1999-01-01.1")
})

test_that("te_clear_cache removes a version", {
  local_fixture()
  folder <- te_download(fixture_version())
  te_clear_cache(fixture_version())
  expect_false(dir.exists(folder))
})

test_that("the newest version is the one published last", {
  table <- data.frame(
    version = c("results-2026-11-30.1", "results-2027-01-15.1"),
    published = c("2026-12-01", "2027-01-20")
  )
  expect_equal(torontoelections:::newest(table), "results-2027-01-15.1")
})
