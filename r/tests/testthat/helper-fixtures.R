# The loaders are tested against one package built from the sample build, in the repository's
# fixtures/ folder. Outside the source tree, TORONTO_ELECTIONS_FIXTURES can name that folder.
fixtures_dir <- function() {
  candidates <- c(
    Sys.getenv("TORONTO_ELECTIONS_FIXTURES"),
    testthat::test_path("..", "..", "..", "fixtures")
  )
  found <- candidates[nzchar(candidates) & file.exists(file.path(candidates, "versions.csv"))]
  if (length(found) == 0) testthat::skip("the fixture package is not available")
  normalizePath(found[[1]])
}

fixture_version <- function() {
  utils::read.csv(file.path(fixtures_dir(), "versions.csv"), colClasses = "character")$version[[1]]
}

fixture_zip <- function() {
  file.path(fixtures_dir(), paste0("toronto-election-records-", fixture_version(), ".zip"))
}

# Point the loader at the fixture registry and a fresh cache, and forget the session's messages.
local_fixture <- function(env = parent.frame()) {
  cache <- withr::local_tempdir(.local_envir = env)
  withr::local_envvar(
    TORONTO_ELECTIONS_REGISTRY = file.path(fixtures_dir(), "versions.csv"),
    TORONTO_ELECTIONS_CACHE = cache,
    .local_envir = env
  )
  torontoelections:::reset_session()
  invisible(cache)
}

schema_fields <- function(table) {
  folder <- withr::local_tempdir()
  utils::unzip(fixture_zip(), exdir = folder)
  descriptor <- jsonlite::fromJSON(
    list.files(folder, "datapackage.json", recursive = TRUE, full.names = TRUE),
    simplifyVector = FALSE
  )
  for (resource in descriptor$resources) {
    if (identical(resource$name, table)) return(resource$schema$fields)
  }
  stop("no table ", table)
}
