#!/usr/bin/env python3
"""Build a hash-locked x86_64/Python 3.11 offline image payload.

Requires an existing wheelhouse. Does not download dependencies or contact OCI.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
from email.parser import BytesParser

DESCRIPTORS = (
    "log_analytics/dashboards/oci_zpr_visibility_dashboard.json",
    "log_analytics/sources/oci_zpr_visibility_json_source.json",
)


RUNTIME_ASSETS = (
    "image/runtime.py", "image/zpr-bootstrap.service",
    "image/zpr-bootstrap.timer", "image/zpr-refresh.service", "image/zpr-refresh.timer",
    "image/zpr-firstboot.service",
)


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def runtime_lock(path: Path) -> dict:
    packages = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^ ]+) --hash=sha256:([a-f0-9]{64})", line)
        if not match:
            raise ValueError("runtime lock row is malformed")
        name, version, digest = match.groups()
        key = normalize(name)
        if key in packages:
            raise ValueError("runtime lock contains duplicate package")
        packages[key] = (version, digest)
    if not packages:
        raise ValueError("runtime lock is empty")
    return packages


def validate_runtime_wheels(wheels: Path, lock_path: Path) -> None:
    expected = runtime_lock(lock_path)
    actual = {}
    for wheel in wheels.glob("*.whl"):
        with zipfile.ZipFile(wheel) as archive:
            metadata_path = next((name for name in archive.namelist()
                                  if name.endswith(".dist-info/METADATA")), None)
            if metadata_path is None:
                raise ValueError("wheel is missing distribution metadata")
            metadata = BytesParser().parsebytes(archive.read(metadata_path))
        name, version = metadata.get("Name"), metadata.get("Version")
        key = normalize(name or "")
        if not key or key in actual:
            raise ValueError("wheelhouse has a missing or duplicate package identity")
        actual[key] = (version, hashlib.sha256(wheel.read_bytes()).hexdigest())
    if actual != expected:
        missing = set(expected) - set(actual)
        extra = set(actual) - set(expected)
        bad = {name for name in set(actual) & set(expected) if actual[name] != expected[name]}
        raise ValueError("wheelhouse does not match locked runtime packages "
                         f"(missing={len(missing)}, extra={len(extra)}, hash_or_version_mismatch={len(bad)})")


def copy_image_assets(root: Path, output: Path) -> None:
    for name in (*DESCRIPTORS, *RUNTIME_ASSETS):
        path = root / name
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("image asset symlinks are forbidden")
        if not path.is_file():
            raise ValueError("required image asset is missing")
        destination = output / ("runtime/" + Path(name).name if name.startswith("image/") else name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    wheels = output / "wheels"
    wheels.mkdir()
    for wheel in sorted(args.wheelhouse.glob("*.whl")):
        shutil.copy2(wheel, wheels)
    validate_runtime_wheels(wheels, root / "requirements-runtime.lock")
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
                    "--wheel-dir", str(wheels), str(root)], check=True,
                   env={**os.environ, "SOURCE_DATE_EPOCH": os.environ.get("SOURCE_DATE_EPOCH", "946684800"),
                        "PIP_NO_CACHE_DIR": "1"})
    packages = []
    lock = []
    notices = []
    for wheel in sorted(wheels.glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            metadata = BytesParser().parsebytes(archive.read(next(
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))))
            for name in archive.namelist():
                if ".dist-info/" in name and ("/licenses/" in name or Path(name).name.upper().startswith(("LICENSE", "COPYING", "NOTICE"))) and not name.endswith("/"):
                    notices.append(f"\n--- {wheel.name}: {name} ---\n" + archive.read(name).decode("utf-8", errors="replace"))
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        name, version = metadata["Name"], metadata["Version"]
        lock.append(f"{name}=={version} --hash=sha256:{digest}")
        packages.append({"name": name, "version": version, "sha256": digest,
                         "license": metadata.get("License-Expression") or metadata.get("License") or "REVIEW_REQUIRED"})
    (output / "requirements.lock").write_text("\n".join(lock) + "\n")
    unreviewed = [f"{pkg['name']}=={pkg['version']}" for pkg in packages
                  if pkg["license"] == "REVIEW_REQUIRED"]
    if unreviewed:
        raise ValueError("license metadata missing for packaged components: " + ", ".join(unreviewed))
    (output / "dependency-inventory.json").write_text(json.dumps(packages, indent=2) + "\n")
    (output / "THIRD_PARTY_NOTICES.txt").write_text("License texts and metadata bundled from dependency wheels; publisher review remains required.\n" + "\n".join(notices))
    sbom = {"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
            "components": [{"type": "library", "name": pkg["name"], "version": pkg["version"],
                            "purl": f"pkg:pypi/{pkg['name'].lower().replace('_', '-')}@{pkg['version']}",
                            "licenses": [{"license": {"name": pkg["license"]}}],
                            "hashes": [{"alg": "SHA-256", "content": pkg["sha256"]}]}
                           for pkg in packages]}
    (output / "sbom.cdx.json").write_text(json.dumps(sbom, indent=2) + "\n")
    copy_image_assets(root, output)
    checksums = []
    for item in sorted(output.rglob("*")):
        if item.is_file():
            checksums.append(f"{hashlib.sha256(item.read_bytes()).hexdigest()}  {item.relative_to(output)}")
    (output / "SHA256SUMS").write_text("\n".join(checksums) + "\n")


if __name__ == "__main__":
    main()
