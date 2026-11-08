*! version 0.1.0  torontoelections: download, verify and load Toronto Election Results
*
* torontoelections versions
* torontoelections use TABLE [, version(VERSION) from(PATH) clear]
* torontoelections cite [, version(VERSION)]
* torontoelections cache [, clear]
*
* Files are checked with Stata's own -checksum- command, which computes the POSIX cksum CRC
* that each package's checksums.csv and the registry of versions record.

program define torontoelections
	version 16
	if `"$TORONTOELECTIONS_NOTED"' == "" {
		display as text "note: torontoelections has not yet been tested in Stata; please report" ///
			" problems at https://github.com/alexwolson/toronto-election-records/issues"
		global TORONTOELECTIONS_NOTED 1
	}
	gettoken subcommand 0 : 0, parse(" ,")
	if `"`subcommand'"' == "versions" {
		_te_versions `0'
	}
	else if `"`subcommand'"' == "use" {
		_te_use `0'
	}
	else if `"`subcommand'"' == "cite" {
		_te_cite `0'
	}
	else if `"`subcommand'"' == "cache" {
		_te_cache `0'
	}
	else {
		display as error `"unknown subcommand "`subcommand'"; use versions, use, cite or cache"'
		exit 198
	}
end

* The tables a package holds.
program define _te_tables, rclass
	return local tables "candidacies contests elections people person_id_redirects office_tenures parties districts"
end

* An absolute path with "/" separators and a leading "~" expanded.
program define _te_abspath, rclass
	args path
	local path = subinstr(`"`path'"', "\", "/", .)
	if substr(`"`path'"', 1, 1) == "~" {
		local home : environment HOME
		local path = `"`home'"' + substr(`"`path'"', 2, .)
	}
	local isabs = substr(`"`path'"', 1, 1) == "/" | substr(`"`path'"', 2, 1) == ":"
	if !`isabs' {
		local here = subinstr(`"`c(pwd)'"', "\", "/", .)
		local path `"`here'/`path'"'
	}
	return local path `"`path'"'
end

* Create a folder and every folder above it that is missing.
program define _te_mkdirs
	args path
	local rest `"`path'"'
	local built ""
	while `"`rest'"' != "" {
		gettoken part rest : rest, parse("/")
		local built `"`built'`part'"'
		if `"`part'"' != "/" {
			capture mkdir `"`built'"'
		}
	}
end

* Remove a folder and everything in it.
program define _te_rmtree
	args path
	local files : dir `"`path'"' files "*"
	foreach file of local files {
		erase `"`path'/`file'"'
	}
	capture erase `"`path'/.verified"'
	local dirs : dir `"`path'"' dirs "*"
	foreach dir of local dirs {
		_te_rmtree `"`path'/`dir'"'
	}
	capture rmdir `"`path'"'
	if _rc {
		display as text `"note: could not remove `path'"'
	}
end

* The cache folder: $TORONTOELECTIONS_CACHE, the TORONTO_ELECTIONS_CACHE environment variable,
* or the user cache folder the Python loader uses.
program define _te_cachedir, rclass
	local dir `"$TORONTOELECTIONS_CACHE"'
	if `"`dir'"' == "" {
		local dir : environment TORONTO_ELECTIONS_CACHE
	}
	if `"`dir'"' == "" {
		if "`c(os)'" == "Windows" {
			local base : environment LOCALAPPDATA
			local dir `"`base'/toronto-elections/Cache"'
		}
		else if "`c(os)'" == "MacOSX" {
			local dir "~/Library/Caches/toronto-elections"
		}
		else {
			local base : environment XDG_CACHE_HOME
			if `"`base'"' == "" {
				local base "~/.cache"
			}
			local dir `"`base'/toronto-elections"'
		}
	}
	_te_abspath `"`dir'"'
	local dir `"`r(path)'"'
	_te_mkdirs `"`dir'"'
	return local dir `"`dir'"'
end

* Read the registry of published versions into the frame _te_registry. If it cannot be read,
* the copy kept by the last successful read is used.
program define _te_registry, rclass
	_te_cachedir
	local dir `"`r(dir)'"'
	local source `"$TORONTOELECTIONS_REGISTRY"'
	if `"`source'"' == "" {
		local source : environment TORONTO_ELECTIONS_REGISTRY
	}
	if `"`source'"' == "" {
		local source "https://raw.githubusercontent.com/alexwolson/toronto-election-records/main/versions.csv"
	}
	capture copy `"`source'"' `"`dir'/versions.part"', replace
	if _rc == 0 {
		copy `"`dir'/versions.part"' `"`dir'/versions.csv"', replace
		erase `"`dir'/versions.part"'
	}
	else {
		capture confirm file `"`dir'/versions.csv"'
		if _rc {
			display as error `"cannot read the list of versions at `source'"'
			exit 631
		}
		display as text `"note: cannot read the list of versions at `source'; using the cached copy"'
	}
	capture frame drop _te_registry
	frame create _te_registry
	frame _te_registry {
		* A registry with no version yet has only its header row.
		capture quietly import delimited using `"`dir'/versions.csv"', varnames(1) ///
			stringcols(_all) encoding("utf-8") clear
		if _rc {
			clear
		}
		if _N > 0 {
			sort published version
		}
	}
	return local dir `"`dir'"'
	return local source `"`source'"'
end

* Check every file of a package against its checksums.csv with -checksum-.
program define _te_verify
	args root
	capture frame drop _te_sums
	frame create _te_sums
	frame _te_sums {
		quietly import delimited using `"`root'/checksums.csv"', varnames(1) stringcols(_all) clear
		local n = _N
		forvalues i = 1/`n' {
			local path = path[`i']
			local bytes = bytes[`i']
			local crc = cksum[`i']
			capture confirm file `"`root'/`path'"'
			if _rc {
				display as error `"`path' is missing from the package"'
				exit 601
			}
			quietly checksum `"`root'/`path'"'
			if r(filelen) != real(`"`bytes'"') | r(checksum) != real(`"`crc'"') {
				display as error `"`path' does not match its checksum in checksums.csv"'
				exit 610
			}
		}
	}
	frame drop _te_sums
end

* The value of a top-level string field on its own line of datapackage.json.
program define _te_json_field, rclass
	args root field
	tempname handle
	file open `handle' using `"`root'/datapackage.json"', read text
	file read `handle' line
	local value ""
	while r(eof) == 0 {
		if ustrregexm(`"`macval(line)'"', `"^  "`field'": "([^"]*)""') {
			local value = ustrregexs(1)
			continue, break
		}
		file read `handle' line
	}
	file close `handle'
	return local value `"`value'"'
end

* Refuse a package schema this release does not read.
program define _te_check_schema
	args schema
	local major = real(substr(`"`schema'"', 1, strpos(`"`schema'"', ".") - 1))
	if `major' > 1 {
		display as error `"This version uses package schema `schema', and this release of"' ///
			`" torontoelections reads schema 1. Update it: ado update torontoelections, update"'
		exit 198
	}
	if `major' < 1 {
		display as error `"This version uses package schema `schema', which this release of"' ///
			" torontoelections no longer reads. Install an older release."
		exit 198
	}
end

* The folder inside FOLDER that holds datapackage.json.
program define _te_top_folder, rclass
	args folder
	capture confirm file `"`folder'/datapackage.json"'
	if _rc == 0 {
		return local root `"`folder'"'
		exit
	}
	local dirs : dir `"`folder'"' dirs "*"
	local count : word count `dirs'
	if `count' != 1 {
		display as error `"`folder' does not hold a Toronto Election Results package"'
		exit 601
	}
	local child : word 1 of `dirs'
	capture confirm file `"`folder'/`child'/datapackage.json"'
	if _rc {
		display as error `"`folder' does not hold a Toronto Election Results package"'
		exit 601
	}
	return local root `"`folder'/`child'"'
end

* Unzip ZIP into FOLDER, then return to the working directory.
program define _te_unzip
	args zip folder
	_te_mkdirs `"`folder'"'
	local here `"`c(pwd)'"'
	quietly cd `"`folder'"'
	capture noisily unzipfile `"`zip'"', replace
	local rc = _rc
	quietly cd `"`here'"'
	if `rc' {
		exit `rc'
	}
end

* The options of _te_resolve, with only those the user gave, after a comma.
program define _te_options, rclass
	args version from
	local options ""
	if `"`version'"' != "" {
		local options `"version(`version')"'
	}
	if `"`from'"' != "" {
		local options `"`options' from(`"`from'"')"'
	}
	if `"`options'"' != "" {
		local options `", `options'"'
	}
	return local options `"`options'"'
end

* Find a version, download and check it if it is not cached, and return its folder.
program define _te_resolve, rclass
	syntax [, Version(string) From(string)]
	if `"`from'"' != "" {
		_te_local `"`from'"'
		return add
		exit
	}
	_te_registry
	local dir `"`r(dir)'"'
	local source `"`r(source)'"'
	frame _te_registry {
		if _N == 0 {
			display as error "No version of Toronto Election Results has been published yet."
			exit 2000
		}
		if `"`version'"' == "" {
			local version = version[_N]
			if !strpos(`" $TORONTOELECTIONS_NAMED "', `" `version' "') {
				display as text `"torontoelections: using version `version', the newest."' ///
					`" Pass version(`version') to pin it."'
				global TORONTOELECTIONS_NAMED `"$TORONTOELECTIONS_NAMED `version'"'
			}
		}
		quietly count if version == `"`version'"'
		if r(N) == 0 {
			display as error `"Version `version' is not among the published versions;"' ///
				" torontoelections versions lists them."
			exit 111
		}
		quietly keep if version == `"`version'"'
		local url = package_url[1]
		local bytes = package_bytes[1]
		local sha = package_sha256[1]
		local crc = package_cksum[1]
		local schema = schema_version[1]
		local published = published[1]
		local doi = doi[1]
	}
	frame drop _te_registry
	_te_check_schema `"`schema'"'

	local folder `"`dir'/`version'"'
	local verified 0
	capture confirm file `"`folder'/.verified"'
	if _rc == 0 {
		tempname handle
		file open `handle' using `"`folder'/.verified"', read text
		file read `handle' marker
		file close `handle'
		if `"`marker'"' == `"`sha'"' {
			local verified 1
		}
	}
	if !`verified' {
		local isurl = strpos(`"`url'"', "://") > 0
		local isabs = substr(`"`url'"', 1, 1) == "/" | substr(`"`url'"', 2, 1) == ":"
		if !`isurl' & !`isabs' {
			local base = substr(`"`source'"', 1, strrpos(subinstr(`"`source'"', "\", "/", .), "/"))
			local url `"`base'`url'"'
		}
		_te_mkdirs `"`dir'/downloads"'
		local zip `"`dir'/downloads/toronto-election-records-`version'.zip"'
		capture copy `"`url'"' `"`zip'"', replace
		if _rc {
			display as error `"cannot download `url'"'
			exit 631
		}
		quietly checksum `"`zip'"'
		if r(filelen) != real(`"`bytes'"') | r(checksum) != real(`"`crc'"') {
			erase `"`zip'"'
			display as error `"The download of `version' does not match its published checksum."'
			exit 610
		}
		local listed : dir `"`dir'"' dirs `"`version'"'
		if `"`listed'"' != "" {
			_te_rmtree `"`folder'"'
		}
		_te_unzip `"`zip'"' `"`folder'"'
		erase `"`zip'"'
		_te_top_folder `"`folder'"'
		_te_verify `"`r(root)'"'
		tempname handle
		file open `handle' using `"`folder'/.verified"', write text replace
		file write `handle' `"`sha'"'
		file close `handle'
	}
	_te_top_folder `"`folder'"'
	return local root `"`r(root)'"'
	return local version `"`version'"'
	return local published `"`published'"'
	return local doi `"`doi'"'
end

* A package the user already has: a ZIP or a folder.
program define _te_local, rclass
	args from
	_te_abspath `"`from'"'
	local from `"`r(path)'"'
	capture confirm file `"`from'/datapackage.json"'
	local isdir = _rc == 0
	if !`isdir' {
		local subdirs ""
		capture local subdirs : dir `"`from'"' dirs "*"
		local isdir = `"`subdirs'"' != ""
	}
	if `isdir' {
		_te_top_folder `"`from'"'
		local root `"`r(root)'"'
	}
	else {
		capture confirm file `"`from'"'
		if _rc {
			display as error `"`from' does not exist"'
			exit 601
		}
		quietly checksum `"`from'"'
		local crc = r(checksum)
		_te_cachedir
		local base `"`r(dir)'"'
		local folder `"`base'/local-`crc'"'
		local listed : dir `"`base'"' dirs `"local-`crc'"'
		if `"`listed'"' == "" {
			_te_unzip `"`from'"' `"`folder'"'
		}
		_te_top_folder `"`folder'"'
		local root `"`r(root)'"'
	}
	_te_json_field `"`root'"' schema_version
	_te_check_schema `"`r(value)'"'
	_te_verify `"`root'"'
	_te_json_field `"`root'"' version
	local version `"`r(value)'"'
	_te_json_field `"`root'"' created
	return local root `"`root'"'
	return local version `"`version'"'
	return local published `"`r(value)'"'
	return local doi ""
end

program define _te_citation, rclass
	args version published doi
	local year = substr(`"`published'"', 1, 4)
	local text `"Olson, A., & Elliott, M. (`year'). Toronto Election Results (Version `version') [Data set]."'
	if `"`doi'"' != "" {
		local text `"`text' Zenodo. https://doi.org/`doi'"'
	}
	return local text `"`text'"'
	return local year `"`year'"'
end

program define _te_use
	syntax namelist(name=table max=1) [, Version(string) From(string) clear]
	_te_tables
	if !strpos(`" `r(tables)' "', `" `table' "') {
		display as error `"`table' is not a table of Toronto Election Results; the tables are"' ///
			`" `r(tables)'"'
		exit 198
	}
	_te_options `"`version'"' `"`from'"'
	_te_resolve `r(options)'
	local root `"`r(root)'"'
	local loaded `"`r(version)'"'
	local published `"`r(published)'"'
	local doi `"`r(doi)'"'
	if "`clear'" != "" {
		use `"`root'/data/`table'.dta"', clear
	}
	else {
		use `"`root'/data/`table'.dta"'
	}
	if !strpos(`" $TORONTOELECTIONS_CITED "', `" `loaded' "') {
		_te_citation `"`loaded'"' `"`published'"' `"`doi'"'
		display as text `"torontoelections: please cite `r(text)'"'
		global TORONTOELECTIONS_CITED `"$TORONTOELECTIONS_CITED `loaded'"'
	}
end

program define _te_versions, rclass
	syntax
	_te_registry
	frame _te_registry {
		if _N == 0 {
			display as text "No version of Toronto Election Results has been published yet."
			return scalar N = 0
		}
		else {
			list version published doi build_commit, noobs clean
			return scalar N = _N
			return local newest = version[_N]
		}
	}
	frame drop _te_registry
end

program define _te_cite, rclass
	syntax [, Version(string) From(string)]
	_te_options `"`version'"' `"`from'"'
	_te_resolve `r(options)'
	local loaded `"`r(version)'"'
	local doi `"`r(doi)'"'
	_te_citation `"`loaded'"' `"`r(published)'"' `"`doi'"'
	local text `"`r(text)'"'
	local year `"`r(year)'"'
	display as text `"`text'"'
	display as text ""
	display as text `"@dataset{olson_elliott_`year'_toronto,"'
	display as text "  author = {Olson, Alex and Elliott, Matt},"
	display as text "  title = {Toronto Election Results},"
	display as text `"  version = {`loaded'},"'
	display as text `"  year = {`year'},"'
	if `"`doi'"' != "" {
		display as text "  publisher = {Zenodo},"
		display as text `"  doi = {`doi'}"'
	}
	else {
		display as text "  publisher = {Zenodo}"
	}
	display as text "}"
	return local citation `"`text'"'
end

program define _te_cache, rclass
	syntax [, dir clear]
	_te_cachedir
	local base `"`r(dir)'"'
	if "`clear'" != "" {
		local dirs : dir `"`base'"' dirs "*"
		foreach child of local dirs {
			capture confirm file `"`base'/`child'/.verified"'
			if _rc == 0 | substr(`"`child'"', 1, 6) == "local-" | `"`child'"' == "downloads" {
				_te_rmtree `"`base'/`child'"'
			}
		}
		capture erase `"`base'/versions.csv"'
		display as text `"emptied the cache at `base'"'
	}
	else {
		display as text `"`base'"'
	}
	return local dir `"`base'"'
end
