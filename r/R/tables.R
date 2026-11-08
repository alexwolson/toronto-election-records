# Read the tables of a version with R types and the codebook's labels attached.

career_columns <- c(
  "person_id", "candidate_name", "election_date", "election_type", "office_type",
  "represented_body", "district_id", "district_name", "boundary_regime", "party_name",
  "affiliation_status", "votes", "vote_share", "vote_rank", "elected", "acclaimed", "incumbent",
  "candidacy_id", "contest_id"
)

table_fields <- function(descriptor, table) {
  for (resource in descriptor$resources) {
    if (identical(resource$name, table) && !is.null(resource$schema)) return(resource$schema$fields)
  }
  stop("This version has no table named ", table, ".", call. = FALSE)
}

as_type <- function(x, type) {
  switch(type,
    string = as.character(x),
    integer = as.integer(x),
    number = as.double(x),
    boolean = as.logical(x),
    date = as.Date(x),
    stop("unknown column type ", type, call. = FALSE)
  )
}

read_table <- function(table, version) {
  resolved <- resolve(version)
  cite_once(resolved$descriptor, resolved$row)
  fields <- table_fields(resolved$descriptor, table)
  path <- file.path(resolved$root, "data", paste0(table, ".parquet"))
  frame <- as.data.frame(nanoparquet::read_parquet(path))
  if (!identical(names(frame), vapply(fields, function(f) f$name, ""))) {
    stop(table, ".parquet does not have the columns datapackage.json lists.", call. = FALSE)
  }
  for (field in fields) {
    column <- as_type(frame[[field$name]], field$type)
    attr(column, "label") <- field$title
    attr(column, "description") <- field$description
    frame[[field$name]] <- column
  }
  attr(frame, "table") <- table
  attr(frame, "version") <- resolved$descriptor$version
  frame
}

# Rows of a table, keeping the columns' labels, which `[` drops.
keep_rows <- function(frame, rows) {
  out <- frame[rows, , drop = FALSE]
  for (name in names(frame)) {
    for (what in c("label", "description")) attr(out[[name]], what) <- attr(frame[[name]], what)
  }
  rownames(out) <- NULL
  attr(out, "table") <- attr(frame, "table")
  attr(out, "version") <- attr(frame, "version")
  out
}

#' Candidacies: one row per candidate in one Contest
#'
#' @inheritParams te_download
#' @param source_confirmed_only If `TRUE`, `person_id` is `NA` where the link to the Person rests
#'   only on the build's structural rules (`person_link_basis == "structural"`).
#' @param bodies,offices,years Keep only the rows with these values of `represented_body`,
#'   `office_type` and `election_year`.
#' @return A data frame. Each column carries the codebook's `label` and `description` attributes.
#' @export
te_candidacies <- function(version = NULL, source_confirmed_only = FALSE, bodies = NULL,
                           offices = NULL, years = NULL) {
  frame <- read_table("candidacies", version)
  if (source_confirmed_only) {
    frame$person_id[frame$person_link_basis %in% "structural"] <- NA_character_
  }
  keep <- rep(TRUE, nrow(frame))
  if (!is.null(bodies)) keep <- keep & frame$represented_body %in% bodies
  if (!is.null(offices)) keep <- keep & frame$office_type %in% offices
  if (!is.null(years)) keep <- keep & frame$election_year %in% as.integer(years)
  if (all(keep)) frame else keep_rows(frame, keep)
}

#' Contests: one row per Contest
#' @inheritParams te_download
#' @return A data frame.
#' @export
te_contests <- function(version = NULL) read_table("contests", version)

#' Election events: one row per general election or by-election
#' @inheritParams te_download
#' @return A data frame.
#' @export
te_elections <- function(version = NULL) read_table("elections", version)

#' Parties: one row per registered party
#' @inheritParams te_download
#' @return A data frame.
#' @export
te_parties <- function(version = NULL) read_table("parties", version)

#' People: one row per active Person, with their external IDs
#' @inheritParams te_download
#' @return A data frame.
#' @export
te_people <- function(version = NULL) read_table("people", version)

#' Retired Person IDs and the IDs that replaced them
#' @inheritParams te_download
#' @return A data frame.
#' @export
te_person_id_redirects <- function(version = NULL) read_table("person_id_redirects", version)

#' Office tenures: evidence that a Person held an office
#' @inheritParams te_download
#' @return A data frame.
#' @export
te_office_tenures <- function(version = NULL) read_table("office_tenures", version)

#' Districts: one row per ward, riding or trustee area
#'
#' @inheritParams te_download
#' @param geometry If `TRUE`, return an `sf` object with each district's shape in EPSG:4326, and
#'   an empty shape where the release has none. Needs the sf package.
#' @return A data frame, or an `sf` object.
#' @export
te_districts <- function(version = NULL, geometry = FALSE) {
  frame <- read_table("districts", version)
  if (!geometry) return(frame)
  if (!requireNamespace("sf", quietly = TRUE)) {
    stop("The shapes need the sf package: install.packages(\"sf\")", call. = FALSE)
  }
  path <- file.path(resolve(version)$root, "data", "districts.gpkg")
  shapes <- sf::st_read(path, layer = "districts", quiet = TRUE)
  shapes <- sf::st_transform(shapes, 4326)
  at <- match(frame$district_id, shapes$district_id)
  drawn <- sf::st_geometry(shapes)
  geometries <- lapply(at, function(i) if (is.na(i)) sf::st_multipolygon() else drawn[[i]])
  sf::st_sf(frame, geometry = sf::st_sfc(geometries, crs = 4326))
}

#' The current Person ID of each ID
#'
#' @param ids Person IDs, retired or current.
#' @inheritParams te_download
#' @return A character vector: the current ID for each, or `NA` for an ID the version does not
#'   know.
#' @export
te_resolve_person_id <- function(ids, version = NULL) {
  redirects <- te_person_id_redirects(version)
  active <- te_people(version)$person_id
  current <- redirects$person_id[match(ids, redirects$retired_person_id)]
  ifelse(!is.na(current), current, ifelse(ids %in% active, ids, NA_character_))
}

#' Careers: each run of the given People, in date order
#'
#' @param person_id One or more Person IDs, retired or current.
#' @inheritParams te_download
#' @return A data frame with one row per Candidacy: the office, district, party, result and
#'   incumbency of each run.
#' @export
te_careers <- function(person_id, version = NULL) {
  current <- unique(stats::na.omit(te_resolve_person_id(person_id, version)))
  frame <- te_candidacies(version)
  runs <- frame[, career_columns, drop = FALSE]
  chosen <- which(runs$person_id %in% current)
  chosen <- chosen[order(runs$person_id[chosen], runs$election_date[chosen], runs$candidacy_id[chosen])]
  keep_rows(runs, chosen)
}

#' The codebook of one table
#'
#' @param table A table name, such as `"candidacies"`.
#' @inheritParams te_download
#' @return A data frame with one row per column: its type, label, description, allowed values,
#'   what a null means, and units.
#' @export
te_codebook <- function(table, version = NULL) {
  fields <- table_fields(resolve(version)$descriptor, table)
  value_of <- function(f, name) if (is.null(f[[name]])) "" else as.character(f[[name]])
  data.frame(
    column = vapply(fields, function(f) f$name, ""),
    type = vapply(fields, function(f) f$type, ""),
    label = vapply(fields, function(f) f$title, ""),
    description = vapply(fields, function(f) f$description, ""),
    values = vapply(fields, function(f) paste(unlist(f$constraints$enum), collapse = ", "), ""),
    null_meaning = vapply(fields, function(f) f$null_meaning, ""),
    units = vapply(fields, function(f) value_of(f, "units"), "")
  )
}
