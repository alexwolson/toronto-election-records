"""te-package: build, publish and register versions of the user package.

    te-package build                          build both ZIPs from build.toml
    te-package publish [--sandbox] [--previous ID]
                                              make a Zenodo draft holding both ZIPs
    te-package register --record ID [--sandbox --registry PATH]
                                              add a published record to versions.csv
    te-package dataverse --build-root PATH --doi DOI
                                              assemble the Dataverse deposit

`publish` reads the token from ZENODO_TOKEN, or ZENODO_SANDBOX_TOKEN with --sandbox. It stops at
a draft: review the draft on Zenodo and publish it there, then run `register`.
"""

from __future__ import annotations

import argparse
import json
import os
import tomllib
from pathlib import Path

from te_package.assemble import build_package
from te_package.build_input import load_pin
from te_package.codebook import REPO_ROOT
from te_package.publish import ZENODO, Zenodo, dataverse_folder, publish_draft, register


def _settings(pin_path: Path):
    pin = load_pin(pin_path)
    config = tomllib.loads(pin_path.read_text(encoding="utf-8"))
    return pin, config.get("validation", {}).get("audited_links_sha256") or None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="te-package", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("build", "build the package and the supplement"),
        ("publish", "make a Zenodo draft that holds both ZIPs"),
        ("dataverse", "assemble the Dataverse deposit"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--pin", type=Path, default=REPO_ROOT / "build.toml")
        command.add_argument("--out", type=Path, default=REPO_ROOT / "dist")
        command.add_argument("--cache", type=Path, default=REPO_ROOT / ".cache" / "build")
    publish = sub.choices["publish"]
    publish.add_argument("--sandbox", action="store_true", help="use sandbox.zenodo.org")
    publish.add_argument("--previous", type=int, help="the ID of the latest published version")
    deposit = sub.choices["dataverse"]
    deposit.add_argument(
        "--build-root",
        type=Path,
        required=True,
        help="a checkout of the build at the pinned commit, with data/raw/",
    )
    deposit.add_argument("--doi", required=True, help="the version's Zenodo DOI")
    reg = sub.add_parser("register", help="add a published Zenodo record to versions.csv")
    reg.add_argument("--record", type=int, required=True)
    reg.add_argument("--sandbox", action="store_true")
    reg.add_argument("--registry", type=Path, default=REPO_ROOT / "versions.csv")
    args = parser.parse_args(argv)

    if args.command == "build":
        pin, audited = _settings(args.pin)
        built = build_package(pin, args.cache, args.out, audited)
        print(f"version {built.version}")
        print(f"package    {built.package_zip} ({built.package_zip.stat().st_size:,} bytes)")
        print(f"supplement {built.supplement_zip} ({built.supplement_zip.stat().st_size:,} bytes)")
    elif args.command == "publish":
        variable = "ZENODO_SANDBOX_TOKEN" if args.sandbox else "ZENODO_TOKEN"
        token = os.environ.get(variable)
        if not token:
            raise SystemExit(f"set {variable} to a Zenodo token with the deposit scopes")
        pin, audited = _settings(args.pin)
        client = Zenodo(ZENODO["sandbox" if args.sandbox else "live"], token)
        result = publish_draft(pin, args.cache, args.out, audited, client, args.previous)
        print(f"draft      {result.draft.html}")
        print(f"DOI        {result.draft.doi} (reserved; it resolves once the draft is published)")
        print(f"uploaded   {result.built.package_zip.name}, {result.built.supplement_zip.name}")
        print("Review the draft on Zenodo and publish it there, then run te-package register.")
    elif args.command == "register":
        if args.sandbox and args.registry == REPO_ROOT / "versions.csv":
            raise SystemExit("a sandbox record must not enter versions.csv; pass --registry")
        row = register(ZENODO["sandbox" if args.sandbox else "live"], args.record, args.registry)
        print(f"added {row['version']} ({row['doi']}) to {args.registry}")
    elif args.command == "dataverse":
        pin, _ = _settings(args.pin)
        package = args.out / f"toronto-election-records-{pin.version}.zip"
        supplement = args.out / f"toronto-election-records-{pin.version}-provenance.zip"
        for archive in (package, supplement):
            if not archive.is_file():
                raise SystemExit(f"{archive} is missing; run te-package build first")
        manifest = json.loads(
            (args.build_root / "data" / "out" / "build_manifest.json").read_text(encoding="utf-8")
        )
        out = args.out / f"dataverse-{pin.version}"
        left_out = dataverse_folder(
            package, supplement, manifest, args.build_root, out, pin.version, args.doi
        )
        print(f"wrote {out}")
        for local in left_out:
            print(f"left out {local}: it holds contact details")


if __name__ == "__main__":
    main()
