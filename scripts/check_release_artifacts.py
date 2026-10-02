#!/usr/bin/env python3
"""Reject deployment artifacts that do not match the allowlisted source."""
import argparse
from pathlib import Path
import tempfile
import zipfile

from build_collector_archive import build_archive as build_collector
from build_orm_archive import INPUTS, build_archive as build_orm


def check(root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="zpr-admission-") as temporary:
        expected = Path(temporary).resolve() / "collector.tgz"
        build_collector(root, expected)
        with zipfile.ZipFile(root / "orm-stack.zip") as archive:
            if archive.namelist() != sorted(INPUTS):
                raise ValueError("ORM archive membership differs from allowlist")
            for name in INPUTS:
                path = root / name if name == "requirements-runtime.lock" else root / "orm" / name
                content = expected.read_bytes() if name == "oci_zpr_visibility_pkg.tgz" else path.read_bytes()
                if archive.read(name) != content:
                    raise ValueError(f"ORM artifact differs from source: {name}")
        canonical = Path(temporary) / "orm.zip"
        build_orm(root, canonical, collector=expected)
        if canonical.read_bytes() != (root / "orm-stack.zip").read_bytes():
            raise ValueError("ORM archive bytes or metadata are not canonical")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    check(args.root)
    print("Release artifact allowlist and source parity: passed")
