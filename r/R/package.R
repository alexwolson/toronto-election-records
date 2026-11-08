# Find a version, download it, check it against its checksums and keep it in the cache.

registry_url <- "https://raw.githubusercontent.com/alexwolson/toronto-election-records/main/versions.csv"
supported_schema_major <- 1L
loader_version <- "0.1.0"

.session <- new.env(parent = emptyenv())
.session$named <- character()
.session$cited <- character()

reset_session <- function() {
  .session$named <- character()
  .session$cited <- character()
  invisible(NULL)
}

#' Where downloaded versions are kept
#'
#' The cache is in the user cache folder that [tools::R_user_dir()] gives, unless the
#' environment variable `TORONTO_ELECTIONS_CACHE` names another folder.
#'
#' @return The path of the cache folder.
#' @export
te_cache_dir <- function() {
  folder <- Sys.getenv("TORONTO_ELECTIONS_CACHE")
  if (nzchar(folder)) folder else tools::R_user_dir("torontoelections", "cache")
}

registry_location <- function() {
  location <- Sys.getenv("TORONTO_ELECTIONS_REGISTRY")
  if (nzchar(location)) location else registry_url
}

is_url <- function(x) grepl("^(https?|file)://", x)

fetch_to <- function(source, target) {
  dir.create(dirname(target), recursive = TRUE, showWarnings = FALSE)
  partial <- paste0(target, ".part")
  if (is_url(source)) {
    old <- options(timeout = max(600, getOption("timeout")))
    on.exit(options(old), add = TRUE)
    status <- tryCatch(
      suppressWarnings(utils::download.file(source, partial, mode = "wb", quiet = TRUE)),
      error = function(e) 1L
    )
    if (!identical(as.integer(status), 0L)) {
      unlink(partial)
      stop("Cannot download ", source, call. = FALSE)
    }
  } else if (!file.exists(source) || !file.copy(source, partial, overwrite = TRUE)) {
    stop("Cannot read ", source, call. = FALSE)
  }
  file.rename(partial, target)
  invisible(target)
}

#' Published versions of Toronto Election Results
#'
#' Reads the list of published versions. If it cannot be reached, the copy cached by the last
#' successful read is used, with a warning.
#'
#' @return A data frame with one row per version: its name, publication date, DOI, Zenodo record,
#'   the build commit it was made from, its package schema, and its package's URL, size and
#'   checksums.
#' @export
te_versions <- function() {
  location <- registry_location()
  cached <- file.path(te_cache_dir(), "versions.csv")
  fresh <- tempfile(fileext = ".csv")
  on.exit(unlink(fresh), add = TRUE)
  read_ok <- tryCatch({
    fetch_to(location, fresh)
    TRUE
  }, error = function(e) FALSE)
  if (read_ok) {
    dir.create(dirname(cached), recursive = TRUE, showWarnings = FALSE)
    file.copy(fresh, cached, overwrite = TRUE)
  } else if (file.exists(cached)) {
    warning("Cannot read the list of versions at ", location, "; using the cached copy.",
            call. = FALSE)
  } else {
    stop("Cannot read the list of versions at ", location, call. = FALSE)
  }
  utils::read.csv(cached, colClasses = "character", na.strings = character())
}

newest <- function(table) {
  ordered <- table[order(table$published, table$version), , drop = FALSE]
  ordered$version[[nrow(ordered)]]
}

sha256 <- function(path) digest::digest(file = path, algo = "sha256")

package_url <- function(url, registry) {
  if (is_url(url) || grepl("^(/|[A-Za-z]:)", url)) return(url)
  if (is_url(registry)) return(paste0(sub("[^/]*$", "", registry), url))
  file.path(dirname(registry), url)
}

read_descriptor <- function(root) {
  jsonlite::fromJSON(file.path(root, "datapackage.json"), simplifyVector = FALSE)
}

check_package <- function(root, version = NULL) {
  descriptor <- read_descriptor(root)
  schema <- as.character(descriptor$schema_version)
  major <- as.integer(strsplit(schema, ".", fixed = TRUE)[[1]][[1]])
  if (major > supported_schema_major) {
    stop("This version uses package schema ", schema, ", and this release of torontoelections ",
         "reads schema ", supported_schema_major, ". Install a newer release of torontoelections.",
         call. = FALSE)
  }
  if (major < supported_schema_major) {
    stop("This version uses package schema ", schema, ", which this release of torontoelections ",
         "no longer reads. Install an older release of torontoelections.", call. = FALSE)
  }
  if (!is.null(version) && !identical(descriptor$version, version)) {
    stop("The package holds version ", descriptor$version, ", not ", version, ".", call. = FALSE)
  }
  for (resource in descriptor$resources) {
    for (entry in c(list(resource), unname(resource$formats))) {
      path <- file.path(root, entry$path)
      if (!file.exists(path)) stop(entry$path, " is missing from the package.", call. = FALSE)
      if (file.size(path) != entry$bytes || paste0("sha256:", sha256(path)) != entry$hash) {
        stop(entry$path, " does not match its checksum in datapackage.json.", call. = FALSE)
      }
    }
  }
  descriptor
}

top_folder <- function(folder) {
  if (file.exists(file.path(folder, "datapackage.json"))) return(normalizePath(folder))
  children <- list.dirs(folder, recursive = FALSE)
  if (length(children) != 1 || !file.exists(file.path(children[[1]], "datapackage.json"))) {
    stop(folder, " does not hold a Toronto Election Results package.", call. = FALSE)
  }
  normalizePath(children[[1]])
}

owned <- function(folder) {
  if (normalizePath(dirname(folder)) != normalizePath(te_cache_dir())) {
    stop("Refusing to remove ", folder, ", which is outside the cache.", call. = FALSE)
  }
  folder
}

local_package <- function(path) {
  if (dir.exists(path)) {
    root <- top_folder(path)
  } else {
    folder <- file.path(te_cache_dir(), paste0("local-", substr(sha256(path), 1, 16)))
    if (!dir.exists(folder)) utils::unzip(path, exdir = folder)
    root <- top_folder(folder)
  }
  list(root = root, descriptor = check_package(root), row = NULL)
}

resolve <- function(version = NULL) {
  if (!is.null(version) && file.exists(version)) return(local_package(version))
  table <- te_versions()
  if (nrow(table) == 0) {
    stop("No version of Toronto Election Results has been published yet.", call. = FALSE)
  }
  if (is.null(version)) {
    version <- newest(table)
    if (!version %in% .session$named) {
      message("torontoelections: using version ", version, ", the newest. Pass version = \"",
              version, "\" to pin it.")
      .session$named <- c(.session$named, version)
    }
  }
  row <- table[table$version == version, , drop = FALSE]
  if (nrow(row) == 0) {
    stop("Version ", version, " is not among the published versions; te_versions() lists them.",
         call. = FALSE)
  }
  row <- as.list(row[1, ])
  folder <- file.path(te_cache_dir(), version)
  marker <- file.path(folder, ".verified")
  if (file.exists(marker) && identical(readLines(marker, warn = FALSE)[1], row$package_sha256)) {
    root <- top_folder(folder)
    return(list(root = root, descriptor = read_descriptor(root), row = row))
  }
  zip <- file.path(te_cache_dir(), "downloads", paste0("toronto-election-records-", version, ".zip"))
  fetch_to(package_url(row$package_url, registry_location()), zip)
  if (file.size(zip) != as.numeric(row$package_bytes) || sha256(zip) != row$package_sha256) {
    unlink(zip)
    stop("The download of ", version, " does not match its published SHA-256.", call. = FALSE)
  }
  if (dir.exists(folder)) unlink(owned(folder), recursive = TRUE)
  utils::unzip(zip, exdir = folder)
  unlink(zip)
  root <- top_folder(folder)
  descriptor <- check_package(root, version)
  writeLines(row$package_sha256, marker)
  list(root = root, descriptor = descriptor, row = row)
}

#' Download and check a version
#'
#' Downloads a version if it is not in the cache, checks the download against its published
#' size and SHA-256 and every data file against `datapackage.json`, and keeps it in the cache.
#'
#' @param version A published version such as `"results-2026-11-30.1"`, or the path of a package
#'   ZIP or folder. Without it, the newest version is used.
#' @return The path of the folder that holds the version's files.
#' @export
te_download <- function(version = NULL) {
  resolve(version)$root
}

#' Empty the cache
#'
#' @param version One version to remove. Without it, every cached version and the cached list of
#'   versions are removed.
#' @return Nothing.
#' @export
te_clear_cache <- function(version = NULL) {
  base <- te_cache_dir()
  if (!dir.exists(base)) return(invisible(NULL))
  if (!is.null(version)) {
    folder <- file.path(base, version)
    if (dir.exists(folder)) unlink(owned(folder), recursive = TRUE)
    return(invisible(NULL))
  }
  for (child in list.files(base, full.names = TRUE)) {
    name <- basename(child)
    if (dir.exists(child) &&
        (file.exists(file.path(child, ".verified")) || startsWith(name, "local-") ||
         name == "downloads")) {
      unlink(owned(child), recursive = TRUE)
    } else if (name == "versions.csv") {
      unlink(child)
    }
  }
  invisible(NULL)
}

citation_parts <- function(descriptor, row) {
  version <- descriptor$version
  published <- if (!is.null(row) && nzchar(row$published)) row$published else descriptor$created
  year <- substr(published, 1, 4)
  doi <- if (is.null(row)) "" else row$doi
  text <- paste0("Olson, A., & Elliott, M. (", year, "). Toronto Election Results (Version ",
                 version, ") [Data set].", if (nzchar(doi)) paste0(" Zenodo. https://doi.org/", doi) else "")
  bibtex <- paste0(
    "@dataset{olson_elliott_", year, "_toronto,\n",
    "  author = {Olson, Alex and Elliott, Matt},\n",
    "  title = {Toronto Election Results},\n",
    "  version = {", version, "},\n",
    "  year = {", year, "},\n",
    "  publisher = {Zenodo}",
    if (nzchar(doi)) paste0(",\n  doi = {", doi, "}") else "",
    "\n}"
  )
  loader <- paste0("Olson, A. (2026). torontoelections (Version ", loader_version,
                   ") [Computer software]. https://github.com/alexwolson/toronto-election-records")
  list(text = text, bibtex = bibtex, loader = loader)
}

cite_once <- function(descriptor, row) {
  version <- descriptor$version
  if (version %in% .session$cited) return(invisible(NULL))
  .session$cited <- c(.session$cited, version)
  message("torontoelections: please cite ", citation_parts(descriptor, row)$text)
  invisible(NULL)
}

#' Cite a version
#'
#' @inheritParams te_download
#' @return The citation of the version, its BibTeX entry and the citation of this package, as one
#'   string. Print it with [cat()].
#' @export
te_cite <- function(version = NULL) {
  resolved <- resolve(version)
  parts <- citation_parts(resolved$descriptor, resolved$row)
  paste0(parts$text, "\n\n", parts$bibtex, "\n\nThe data were loaded with:\n", parts$loader)
}
