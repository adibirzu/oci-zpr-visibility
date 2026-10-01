#!/usr/bin/env python3
"""Build deterministic collector bytes so unchanged source causes no upgrade."""
import argparse
import gzip
import os
from pathlib import Path
import tarfile
import tempfile

DESCRIPTORS = ("log_analytics/dashboards/oci_zpr_visibility_dashboard.json",
               "log_analytics/sources/oci_zpr_visibility_json_source.json")


def build_archive(root: Path, output: Path) -> None:
    # Only importable modules and reviewed descriptors belong in this package.
    # Do not recursively include arbitrary files from source directories.
    files = [root / "pyproject.toml", root / "README.md", root / "requirements-runtime.lock"]
    files.extend((root / "oci_zpr_visibility").glob("*.py"))
    files.extend(root / name for name in DESCRIPTORS)
    mandatory = [root / "pyproject.toml", root / "README.md", root / "requirements-runtime.lock",
                 root / "oci_zpr_visibility/__init__.py",
                 *(root / name for name in DESCRIPTORS)]
    if any(not path.is_file() for path in mandatory):
        raise ValueError("missing mandatory collector input")
    for path in files:
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("collector inputs must not contain symlinks")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".collector-", suffix=".tgz", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
                with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    for path in sorted(files):
                        info = archive.gettarinfo(str(path), arcname=str(path.relative_to(root)))
                        info.uid = info.gid = info.mtime = 0
                        info.uname = info.gname = ""
                        info.mode = 0o644
                        with path.open("rb") as content:
                            archive.addfile(info, content)
        os.replace(temporary, output)
        # OCI's source diff includes filesystem mtime, not only archive content.
        os.utime(output, (946684800, 946684800))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_archive(args.root, args.output)
