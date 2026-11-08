"""Find a version, download it, check it against its checksums and keep it in the cache."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import warnings
import zipfile
from pathlib import Path

import pandas as pd
import platformdirs

REGISTRY_URL = (
    "https://raw.githubusercontent.com/alexwolson/toronto-election-records/main/versions.csv"
)
SUPPORTED_SCHEMA_MAJOR = 1
LOADER_VERSION = "0.1.0"

_session: dict[str, set[str]] = {"named": set(), "cited": set()}


class LoaderError(Exception):
    """A version cannot be found, downloaded or read."""


def reset_session() -> None:
    """Forget which versions this session has named and cited (used by the tests)."""

    for seen in _session.values():
        seen.clear()


def cache_dir() -> Path:
    """The folder where downloaded versions are kept."""

    return Path(
        os.environ.get("TORONTO_ELECTIONS_CACHE")
        or platformdirs.user_cache_dir("toronto-elections")
    )


def _registry_location() -> str:
    return os.environ.get("TORONTO_ELECTIONS_REGISTRY") or REGISTRY_URL


def _is_url(text: str) -> bool:
    return urllib.parse.urlparse(text).scheme in {"http", "https", "file"}


def _fetch(location: str) -> bytes:
    if _is_url(location):
        with urllib.request.urlopen(location, timeout=60) as response:
            return response.read()
    return Path(location).read_bytes()


def versions() -> pd.DataFrame:
    """The published versions, with their dates, DOIs and the build each was made from."""

    location = _registry_location()
    cached = cache_dir() / "versions.csv"
    try:
        data = _fetch(location)
    except OSError as error:
        if not cached.is_file():
            raise LoaderError(f"Cannot read the list of versions at {location}: {error}") from error
        warnings.warn(
            f"Cannot read the list of versions at {location}; using the cached copy.",
            UserWarning,
            stacklevel=2,
        )
        data = cached.read_bytes()
    else:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
    return pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)


def newest(table: pd.DataFrame) -> str:
    """The version published last."""

    return table.sort_values(["published", "version"]).version.iloc[-1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_url(package_url: str, registry: str) -> str:
    """The package's URL; a bare file name is read next to the registry."""

    if _is_url(package_url) or Path(package_url).is_absolute():
        return package_url
    if _is_url(registry):
        return urllib.parse.urljoin(registry, package_url)
    return str(Path(registry).parent / package_url)


def _get(source: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    if _is_url(source):
        with urllib.request.urlopen(source, timeout=600) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out)
    else:
        shutil.copyfile(source, partial)
    partial.replace(target)


def _check_package(root: Path, version: str | None) -> dict:
    """Check the schema version and every data file's size and SHA-256; return the descriptor."""

    descriptor = json.loads((root / "datapackage.json").read_text(encoding="utf-8"))
    schema = str(descriptor.get("schema_version", "0"))
    major = int(schema.split(".")[0])
    if major > SUPPORTED_SCHEMA_MAJOR:
        raise LoaderError(
            f"This version uses package schema {schema}, and this release of toronto-elections "
            f"reads schema {SUPPORTED_SCHEMA_MAJOR}. Install a newer release of toronto-elections."
        )
    if major < SUPPORTED_SCHEMA_MAJOR:
        raise LoaderError(
            f"This version uses package schema {schema}, which this release of toronto-elections "
            "no longer reads. Install an older release of toronto-elections."
        )
    if version is not None and descriptor.get("version") != version:
        raise LoaderError(f"The package holds version {descriptor.get('version')}, not {version}.")
    for resource in descriptor["resources"]:
        for entry in [resource, *resource.get("formats", {}).values()]:
            path = root / entry["path"]
            if not path.is_file():
                raise LoaderError(f"{entry['path']} is missing from the package.")
            if path.stat().st_size != entry["bytes"] or "sha256:" + _sha256(path) != entry["hash"]:
                raise LoaderError(
                    f"{entry['path']} does not match its checksum in datapackage.json."
                )
    return descriptor


def _top_folder(folder: Path) -> Path:
    if (folder / "datapackage.json").is_file():
        return folder
    children = [p for p in folder.iterdir() if p.is_dir()]
    if len(children) != 1 or not (children[0] / "datapackage.json").is_file():
        raise LoaderError(f"{folder} does not hold a Toronto Election Results package.")
    return children[0]


def _owned(folder: Path) -> Path:
    """Refuse to remove anything but a direct child of the cache."""

    if folder.parent != cache_dir():
        raise LoaderError(f"Refusing to remove {folder}, which is outside the cache.")
    return folder


def _local(path: Path) -> tuple[Path, dict, None]:
    if path.is_dir():
        root = _top_folder(path)
    else:
        folder = cache_dir() / f"local-{_sha256(path)[:16]}"
        if not folder.is_dir():
            with zipfile.ZipFile(path) as archive:
                archive.extractall(folder)
        root = _top_folder(folder)
    return root, _check_package(root, None), None


def resolve(version: str | os.PathLike | None) -> tuple[Path, dict, pd.Series | None]:
    """The checked package folder of a version, its descriptor and its registry row."""

    if version is not None and (isinstance(version, os.PathLike) or Path(str(version)).exists()):
        return _local(Path(version))
    table = versions()
    if table.empty:
        raise LoaderError("No version of Toronto Election Results has been published yet.")
    if version is None:
        version = newest(table)
        if version not in _session["named"]:
            print(
                f"torontoelections: using version {version}, the newest. "
                f"Pass version='{version}' to pin it.",
                file=sys.stderr,
            )
            _session["named"].add(version)
    rows = table.loc[table.version.eq(version)]
    if rows.empty:
        raise LoaderError(
            f"Version {version} is not among the published versions; versions() lists them."
        )
    row = rows.iloc[0]
    folder = cache_dir() / version
    marker = folder / ".verified"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == row.package_sha256:
        root = _top_folder(folder)
        return root, json.loads((root / "datapackage.json").read_text(encoding="utf-8")), row
    archive = cache_dir() / "downloads" / f"toronto-election-records-{version}.zip"
    _get(_package_url(row.package_url, _registry_location()), archive)
    if archive.stat().st_size != int(row.package_bytes) or _sha256(archive) != row.package_sha256:
        archive.unlink()
        raise LoaderError(f"The download of {version} does not match its published SHA-256.")
    if folder.exists():
        shutil.rmtree(_owned(folder))
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(folder)
    archive.unlink()
    root = _top_folder(folder)
    descriptor = _check_package(root, version)
    marker.write_text(row.package_sha256, encoding="utf-8")
    return root, descriptor, row


def download(version: str | os.PathLike | None = None) -> Path:
    """Download and check a version if it is not cached; return the folder of its files."""

    return resolve(version)[0]


def clear_cache(version: str | None = None) -> None:
    """Remove one cached version, or every version and the cached list of versions."""

    base = cache_dir()
    if not base.is_dir():
        return
    if version is not None:
        if (base / version).exists():
            shutil.rmtree(_owned(base / version))
        return
    for child in base.iterdir():
        if child.is_dir() and ((child / ".verified").is_file() or child.name.startswith("local-")):
            shutil.rmtree(_owned(child))
        elif child.name == "downloads" and child.is_dir():
            shutil.rmtree(_owned(child))
        elif child.name == "versions.csv":
            child.unlink()


def _citation(descriptor: dict, row: pd.Series | None) -> tuple[str, str, str]:
    version = descriptor["version"]
    published = row.published if row is not None and row.published else descriptor["created"]
    year = str(published)[:4]
    doi = row.doi if row is not None else ""
    text = (
        f"Olson, A., & Elliott, M. ({year}). Toronto Election Results (Version {version}) "
        "[Data set]."
    )
    text += f" Zenodo. https://doi.org/{doi}" if doi else ""
    bibtex = (
        f"@dataset{{olson_elliott_{year}_toronto,\n"
        "  author = {Olson, Alex and Elliott, Matt},\n"
        "  title = {Toronto Election Results},\n"
        f"  version = {{{version}}},\n"
        f"  year = {{{year}}},\n"
        "  publisher = {Zenodo}" + (f",\n  doi = {{{doi}}}" if doi else "") + "\n}"
    )
    loader = (
        f"Olson, A. (2026). toronto-elections (Version {LOADER_VERSION}) [Computer software]. "
        "https://github.com/alexwolson/toronto-election-records"
    )
    return text, bibtex, loader


def cite_once(descriptor: dict, row: pd.Series | None) -> None:
    """Print the citation of a version the first time this session loads it."""

    version = descriptor["version"]
    if version in _session["cited"]:
        return
    _session["cited"].add(version)
    text, _, _ = _citation(descriptor, row)
    print(f"torontoelections: please cite {text}", file=sys.stderr)


def cite(version: str | os.PathLike | None = None) -> str:
    """The citation of a version, its BibTeX and the citation of this package."""

    _, descriptor, row = resolve(version)
    text, bibtex, loader = _citation(descriptor, row)
    return f"{text}\n\n{bibtex}\n\nThe data were loaded with:\n{loader}"
