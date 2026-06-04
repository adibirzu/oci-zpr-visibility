#!/usr/bin/env bash
# Build the Oracle Resource Manager stack zip (terraform at zip root + package tarball).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "Building collector package tarball..."
tar czf orm/oci_zpr_visibility_pkg.tgz oci_zpr_visibility pyproject.toml README.md log_analytics
echo "Packaging ORM stack zip..."
rm -f orm-stack.zip
( cd orm && zip -r ../orm-stack.zip . -x '.terraform/*' '*.tfstate*' '.terraform.lock.hcl' >/dev/null )
echo "Wrote $ROOT/orm-stack.zip"
unzip -l orm-stack.zip | tail -20
