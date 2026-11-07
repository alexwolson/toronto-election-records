# torontoelections for Stata

A Stata command that downloads a version of Toronto Election Results, checks every file with
Stata's own `checksum` command, keeps it in a cache, and loads one table at a time. It needs
Stata 16 or later and nothing else.

```stata
net install torontoelections, from("https://raw.githubusercontent.com/alexwolson/toronto-election-records/main/stata")
torontoelections versions
torontoelections use candidacies, version(results-2026-11-30.1) clear
torontoelections cite, version(results-2026-11-30.1)
```

`help torontoelections` documents the subcommands and options.

## Status: not yet run in Stata

The command has been written and read line by line, but it has never been run, because no Stata
licence was available while it was written. These parts are checked without Stata:

- The `.dta` files it loads. ReadStat, an implementation of Stata's format independent of the
  pandas writer that makes them, reads every table of the package as format 118 (Stata 14 or
  later) with the codebook's variable names and labels, `false`/`true` value labels on booleans,
  `%td` dates and the same values as the Parquet files (`packaging/tests/test_package.py`).
- The checksums it compares. Stata's manual says `checksum` "calculates a CRC checksum following
  the POSIX 1003.2 specification and ... produces the same results as the Unix cksum command".
  The packager's CRC, which writes `checksums.csv` and the registry's `package_cksum`, is tested
  against `cksum` itself.

What only Stata can check is the command: the download with `copy`, the checksum comparisons,
`unzipfile`, the cache, the options and the error codes.

## Testing it

With Stata 16 or later, from the root of a clone of this repository (no network is needed):

```stata
do stata/tests/test_torontoelections.do
```

then compare every exported value with the Python loader:

```sh
uv run --project python python stata/tests/compare_exports.py
```

The do-file loads each table from the fixture package, checks its rows and variables against the
package's CSV file, checks the value labels, `from()`, an unknown table, an unknown version, a
download that fails its checksum, the citation and clearing the cache, and exports each table to
`stata/tests/out/`. Someone with Stata can run it and send the `out/` folder back for the
comparison.
