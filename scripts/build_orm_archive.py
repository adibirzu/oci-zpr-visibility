#!/usr/bin/env python3
"""Build an allowlisted, deterministic Resource Manager ZIP atomically."""
import argparse
import os
from pathlib import Path
import tempfile
import zipfile

# Adding a deployment input requires an explicit review of this list.
INPUTS = (
    ".terraform.lock.hcl", "cloudinit/controller.sh.tftpl", "compute.tf",
    "controller.tf", "functions.tf", "loganalytics.tf", "network.tf",
    "oci_zpr_visibility_pkg.tgz", "outputs.tf", "provider.tf", "schema.yaml",
    "storage.tf", "variables.tf", "versions.tf", "zpr.tf", "requirements-runtime.lock",
    "rm_lifecycle.py",
)


def build_archive(root: Path, output: Path, *, collector: Path | None = None) -> None:
    source = root / "orm"
    paths = {name: collector if name == "oci_zpr_visibility_pkg.tgz" and collector is not None
             else source / name for name in INPUTS}
    if (root / "requirements-runtime.lock").is_file():
        paths["requirements-runtime.lock"] = root / "requirements-runtime.lock"
    for name in INPUTS:
        path = paths[name]
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError(f"symlink input forbidden: {name}")
        if not path.is_file():
            raise ValueError(f"missing required deployment input: {name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".orm-", suffix=".zip", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as raw:
            with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name in sorted(INPUTS):
                    info = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = 0o100644 << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, paths[name].read_bytes())
        os.replace(temporary, output)
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
