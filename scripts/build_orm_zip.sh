#!/usr/bin/env bash
# Build the Oracle Resource Manager stack zip (terraform at zip root + package tarball).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUTPUT_PATH="${1:-orm-stack.zip}"
if [[ "$OUTPUT_PATH" != /* ]]; then
  OUTPUT_PATH="$ROOT/$OUTPUT_PATH"
fi
echo "Building collector package tarball..."
BUILD_DIR=$(mktemp -d)
trap 'rm -rf "$BUILD_DIR"' EXIT
cp -R oci_zpr_visibility pyproject.toml README.md log_analytics "$BUILD_DIR/"
python3 -m pip wheel --no-deps --no-build-isolation --wheel-dir "$BUILD_DIR" "$BUILD_DIR"
# Install the collector wheel without a build backend or dependency resolution
# on the guest. Terraform embeds the archive digest in the controller bootstrap.
tar --exclude="__pycache__" --exclude="*.pyc" --exclude="*.pyo" --exclude='*.egg-info' --exclude=build -czf orm/oci_zpr_visibility_pkg.tgz -C "$BUILD_DIR" .
echo "Packaging ORM stack zip..."
rm -f "$OUTPUT_PATH"
# Keep .terraform.lock.hcl in the zip so Resource Manager pins the same provider
# version/hashes (reproducible init). Exclude only local state and the provider cache.
( cd orm && zip -r "$OUTPUT_PATH" . -x '.terraform/*' '*.tfstate*' '*.tfstate.*' '__pycache__/*' '*.pyc' >/dev/null )
echo "Wrote $OUTPUT_PATH"
unzip -l "$OUTPUT_PATH" | tail -20
