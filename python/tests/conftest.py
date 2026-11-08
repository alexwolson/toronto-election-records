from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest

FIXTURES = Path(__file__).parents[2] / "fixtures"
REGISTRY = FIXTURES / "versions.csv"
VERSION = pd.read_csv(REGISTRY).version.iloc[0]
PACKAGE = FIXTURES / f"toronto-election-records-{VERSION}.zip"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Point every test at the fixture registry and a fresh cache, and reset session state."""

    import torontoelections

    monkeypatch.setenv("TORONTO_ELECTIONS_REGISTRY", str(REGISTRY))
    monkeypatch.setenv("TORONTO_ELECTIONS_CACHE", str(tmp_path / "cache"))
    torontoelections._package.reset_session()
    yield


@pytest.fixture
def registry_copy(tmp_path):
    """A writable copy of the fixture registry and package, for tests that change them."""

    folder = tmp_path / "registry"
    folder.mkdir()
    shutil.copy2(REGISTRY, folder / "versions.csv")
    shutil.copy2(PACKAGE, folder / PACKAGE.name)
    return folder
