# Write a table's .rds from its Parquet file, or read an .rds back for checking.
#
#   Rscript rds.R write   TABLE.parquet COLUMNS.json TABLE.rds
#   Rscript rds.R inspect TABLE.rds     OUT.parquet  OUT.json
#
# COLUMNS.json lists each column's name, codebook type and label. The .rds holds a data.frame
# whose columns have the R class for their type and a `label` attribute. `inspect` writes the
# values back to Parquet and each column's class and label to JSON.

args <- commandArgs(trailingOnly = TRUE)
mode <- args[[1]]

as_type <- function(x, type, name) {
  switch(type,
    string = as.character(x),
    integer = {
      if (any(abs(x) > .Machine$integer.max, na.rm = TRUE)) {
        stop("column ", name, " has a value too large for an R integer")
      }
      as.integer(x)
    },
    number = as.double(x),
    boolean = as.logical(x),
    date = as.Date(x),
    stop("unknown type ", type, " for column ", name)
  )
}

if (mode == "write") {
  df <- as.data.frame(nanoparquet::read_parquet(args[[2]]))
  columns <- jsonlite::fromJSON(args[[3]], simplifyVector = FALSE)
  if (!identical(names(df), vapply(columns, function(c) c$name, ""))) {
    stop("the Parquet columns differ from the codebook")
  }
  for (col in columns) {
    x <- as_type(df[[col$name]], col$type, col$name)
    attr(x, "label") <- col$label
    df[[col$name]] <- x
  }
  saveRDS(df, args[[4]], compress = "xz", version = 3)
} else if (mode == "inspect") {
  df <- readRDS(args[[2]])
  info <- lapply(df, function(x) list(class = class(x)[[1]], label = attr(x, "label", exact = TRUE)))
  for (name in names(df)) attr(df[[name]], "label") <- NULL
  nanoparquet::write_parquet(df, args[[3]])
  writeLines(jsonlite::toJSON(info, auto_unbox = TRUE, null = "null"), args[[4]])
} else {
  stop("mode must be write or inspect")
}
