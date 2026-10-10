#!/usr/bin/env bash
# Build the Oracle Resource Manager stack zip (terraform at zip root + package tarball).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "Building collector package tarball..."
cp requirements-runtime.lock orm/requirements-runtime.lock
python3.11 scripts/build_collector_archive.py --root "$ROOT" --output orm/oci_zpr_visibility_pkg.tgz
echo "Packaging ORM stack zip..."
python3.11 scripts/build_orm_archive.py --root "$ROOT" --output orm-stack.zip
python3.11 scripts/check_release_artifacts.py
echo "Wrote $ROOT/orm-stack.zip"
unzip -l orm-stack.zip | tail -20
