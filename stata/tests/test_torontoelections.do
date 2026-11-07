* Test the Stata loader against the fixture package, with no network.
*
* Run from the repository root, in Stata 16 or later:
*     do stata/tests/test_torontoelections.do
* then compare every value with the Python loader:
*     uv run --project python python stata/tests/compare_exports.py
*
* The do-file loads each table, checks its rows and variables against the package's CSV file,
* checks the failure cases, and exports each table to stata/tests/out/.

clear all
version 16
set more off

local root `"`c(pwd)'"'
capture confirm file `"`root'/fixtures/versions.csv"'
if _rc {
	display as error "run this do-file from the root of the repository"
	exit 601
}
adopath ++ `"`root'/stata"'
discard

local fixtures `"`root'/fixtures"'
local stamp = subinstr(subinstr("`c(current_time)'", ":", "", .), " ", "", .)
local cache `"`c(tmpdir)'/te-stata-test-`stamp'"'
global TORONTOELECTIONS_REGISTRY `"`fixtures'/versions.csv"'
global TORONTOELECTIONS_CACHE `"`cache'"'
global TORONTOELECTIONS_NAMED ""
global TORONTOELECTIONS_CITED ""

* The registry lists the fixture version.
torontoelections versions
assert r(N) == 1
local version `"`r(newest)'"'

torontoelections cache
local cachedir `"`r(dir)'"'
local package `"`cachedir'/`version'/toronto-election-records-`version'"'
local out `"`root'/stata/tests/out"'
capture mkdir `"`out'"'

* Each table loads with the CSV file's rows and variables, and is exported for comparison.
foreach table in candidacies contests elections people person_id_redirects office_tenures parties districts {
	torontoelections use `table', version(`version') clear
	local n = _N
	assert `n' > 0
	quietly describe, varlist
	local names `"`r(varlist)'"'
	foreach variable of varlist _all {
		local format : format `variable'
		if substr("`format'", 1, 3) == "%td" {
			format `variable' %tdCCYY-NN-DD
		}
	}
	quietly export delimited using `"`out'/`table'.csv"', nolabel replace
	preserve
	quietly import delimited using `"`package'/data/`table'.csv"', varnames(1) ///
		stringcols(_all) case(preserve) clear
	assert _N == `n'
	quietly describe, varlist
	assert `"`r(varlist)'"' == `"`names'"'
	restore
	display as result `"`table': `n' rows"'
}

* Booleans are 0 and 1 with the value labels false and true.
torontoelections use candidacies, version(`version') clear
assert inlist(elected, 0, 1, .)
assert "`: value label elected'" == "elected"
assert "`: label elected 1'" == "true"

* Without version(), the newest version is used.
global TORONTOELECTIONS_NAMED ""
torontoelections use parties, clear
assert _N > 0

* A package the user already has loads with from().
torontoelections use parties, from(`"`fixtures'/toronto-election-records-`version'.zip"') clear
assert _N > 0

* An unknown table and an unknown version are refused.
capture torontoelections use ballots, version(`version') clear
assert _rc == 198
capture torontoelections use parties, version(results-1999-01-01.1) clear
assert _rc == 111

* A package that does not match its published checksum is refused.
frame create _te_test
frame _te_test {
	quietly import delimited using `"`fixtures'/versions.csv"', varnames(1) stringcols(_all) clear
	replace package_cksum = "1"
	replace package_url = `"`fixtures'/toronto-election-records-`version'.zip"'
	quietly export delimited using `"`cachedir'/bad-versions.csv"', replace
}
frame drop _te_test
global TORONTOELECTIONS_REGISTRY `"`cachedir'/bad-versions.csv"'
torontoelections cache, clear
capture torontoelections use parties, version(`version') clear
assert _rc == 610
global TORONTOELECTIONS_REGISTRY `"`fixtures'/versions.csv"'

* The citation names the version.
torontoelections cite, version(`version')
assert strpos(`"`r(citation)'"', `"Toronto Election Results (Version `version')"') > 0

* Clearing the cache removes the version.
torontoelections use parties, version(`version') clear
torontoelections cache, clear
local left : dir `"`cachedir'"' dirs `"`version'"'
assert `"`left'"' == ""

display as result "All Stata loader tests passed. Now run stata/tests/compare_exports.py."
