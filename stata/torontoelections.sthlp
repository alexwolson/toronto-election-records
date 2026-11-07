{smcl}
{* *! version 0.1.0}{...}
{title:Title}

{phang}
{bf:torontoelections} {hline 2} Download, verify and load the Toronto Election Results dataset


{title:Syntax}

{p 8 16 2}
{cmd:torontoelections versions}

{p 8 16 2}
{cmd:torontoelections use} {it:table} [{cmd:,} {opt v:ersion(version)} {opt f:rom(path)} {opt clear}]

{p 8 16 2}
{cmd:torontoelections cite} [{cmd:,} {opt v:ersion(version)} {opt f:rom(path)}]

{p 8 16 2}
{cmd:torontoelections cache} [{cmd:,} {opt clear}]

{pstd}
where {it:table} is one of {cmd:candidacies}, {cmd:contests}, {cmd:elections}, {cmd:people},
{cmd:person_id_redirects}, {cmd:office_tenures}, {cmd:parties} or {cmd:districts}.


{title:Status}

{pstd}
This command has not yet been run in Stata. It is installed from GitHub, not from SSC, until
someone with Stata runs its tests. The .dta files in every version of the dataset do not depend on
it: unzip the package and {cmd:use "data/candidacies.dta"}. Please report problems at
{browse "https://github.com/alexwolson/toronto-election-records/issues"}.


{title:Description}

{pstd}
Toronto Election Results records the candidates and results of the municipal, school board
trustee, federal and provincial elections held within the City of Toronto since 1993, with each
person's runs for office joined under one Person ID.

{pstd}
{cmd:torontoelections versions} lists the published versions, with their dates and DOIs.

{pstd}
{cmd:torontoelections use} loads one table of a version. The first time a version is used, it is
downloaded from Zenodo, checked against its published checksum, unzipped, and every file is
checked against the package's {cmd:checksums.csv} with Stata's own {helpb checksum} command. The
version is then kept in a cache and read from there. Variables carry the codebook's labels, and
booleans are 0 and 1 with the value labels {cmd:false} and {cmd:true}.

{pstd}
{cmd:torontoelections cite} displays the citation of a version and its BibTeX entry.

{pstd}
{cmd:torontoelections cache} displays the cache folder; with {opt clear}, it removes every cached
version.


{title:Options}

{phang}
{opt version(version)} names the version, such as {cmd:results-2026-11-30.1}. Pass it to pin the
data your analysis uses. Without it the newest version is used, and a note says which.

{phang}
{opt from(path)} reads a package ZIP or folder you already have, for working without a connection
to Zenodo. Its files are checked as for a download.

{phang}
{opt clear} replaces the data in memory, as with {helpb use}.


{title:Settings}

{pstd}
The cache is the folder the Python loader uses: {cmd:~/Library/Caches/toronto-elections} on
macOS, {cmd:~/.cache/toronto-elections} on Linux, and {cmd:%LOCALAPPDATA%/toronto-elections/Cache}
on Windows. The environment variable {cmd:TORONTO_ELECTIONS_CACHE} or the global macro
{cmd:TORONTOELECTIONS_CACHE} names another folder. The global macro
{cmd:TORONTOELECTIONS_REGISTRY} names another list of versions, for testing.


{title:Examples}

{phang}{cmd:. torontoelections versions}{p_end}
{phang}{cmd:. torontoelections use candidacies, version(results-2026-11-30.1) clear}{p_end}
{phang}{cmd:. tabulate office_type elected if incumbent == 1}{p_end}
{phang}{cmd:. torontoelections cite, version(results-2026-11-30.1)}{p_end}


{title:Stored results}

{pstd}
{cmd:torontoelections versions} stores {cmd:r(N)}, the number of versions, and {cmd:r(newest)}.
{cmd:torontoelections cite} stores {cmd:r(citation)}. {cmd:torontoelections cache} stores
{cmd:r(dir)}.


{title:Requirements}

{pstd}
Stata 16 or later. No Python or other software is needed.


{title:Author}

{pstd}
Alex Olson, University of Toronto. The dataset is by Alex Olson and Matt Elliott.
{browse "https://github.com/alexwolson/toronto-election-records"}
