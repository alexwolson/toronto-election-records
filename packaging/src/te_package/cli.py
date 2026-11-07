"""te-package build: make the user package and the provenance supplement from build.toml."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from te_package.assemble import build_package
from te_package.build_input import load_pin
from te_package.codebook import REPO_ROOT


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="te-package")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build the package and the supplement")
    build.add_argument("--pin", type=Path, default=REPO_ROOT / "build.toml")
    build.add_argument("--out", type=Path, default=REPO_ROOT / "dist")
    build.add_argument("--cache", type=Path, default=REPO_ROOT / ".cache" / "build")
    args = parser.parse_args(argv)

    pin = load_pin(args.pin)
    config = tomllib.loads(args.pin.read_text(encoding="utf-8"))
    audited = config.get("validation", {}).get("audited_links_sha256") or None
    built = build_package(pin, args.cache, args.out, audited)
    print(f"version {built.version}")
    print(f"package    {built.package_zip} ({built.package_zip.stat().st_size:,} bytes)")
    print(f"supplement {built.supplement_zip} ({built.supplement_zip.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
