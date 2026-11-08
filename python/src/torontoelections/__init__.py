"""Download, verify and load the Toronto Election Results dataset.

Every function takes ``version``: a published version such as ``"results-2026-11-30.1"``, or the
path of a package ZIP or folder. Pass it to pin the data an analysis uses; without it the newest
published version is used.
"""

from torontoelections import _package
from torontoelections._package import LOADER_VERSION as __version__
from torontoelections._package import LoaderError, cache_dir, cite, clear_cache, download, versions
from torontoelections._tables import (
    candidacies,
    careers,
    codebook,
    contests,
    districts,
    elections,
    office_tenures,
    parties,
    people,
    person_id_redirects,
    resolve_person_id,
)

__all__ = [
    "LoaderError",
    "__version__",
    "_package",
    "cache_dir",
    "candidacies",
    "careers",
    "cite",
    "clear_cache",
    "codebook",
    "contests",
    "districts",
    "download",
    "elections",
    "office_tenures",
    "parties",
    "people",
    "person_id_redirects",
    "resolve_person_id",
    "versions",
]
