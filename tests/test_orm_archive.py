import importlib.util
from pathlib import Path
import shutil
import zipfile

import pytest


ROOT = Path(__file__).parents[1]


def builder():
    spec = importlib.util.spec_from_file_location(
        "orm_builder", ROOT / "scripts/build_orm_archive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collector_builder():
    spec = importlib.util.spec_from_file_location(
        "collector_builder", ROOT / "scripts/build_collector_archive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_root(tmp_path, module):
    root = tmp_path / "source"
    for name in module.INPUTS:
        target = root / "orm" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name == "oci_zpr_visibility_pkg.tgz":
            # The package is generated and gitignored; clean checkouts must not
            # rely on a local build having run before the test suite.
            collector_builder().build_archive(ROOT, target)
        else:
            shutil.copyfile(ROOT / "orm" / name, target)
    return root


def test_explicit_allowlist_excludes_local_secrets_and_is_reproducible(tmp_path):
    module = builder()
    root = fixture_root(tmp_path, module)
    for name in ("local.tfvars", "terraform.tfstate", ".env", "key.pem",
                 "receipt.json", "unreviewed.tf", "__pycache__/bad.pyc"):
        path = root / "orm" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("DO_NOT_SHIP")
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    module.build_archive(root, first)
    module.build_archive(root, second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == sorted(module.INPUTS)
        assert all(b"DO_NOT_SHIP" not in archive.read(n) for n in archive.namelist())


def test_missing_input_preserves_previous_artifact(tmp_path):
    module = builder()
    root = fixture_root(tmp_path, module)
    (root / "orm/schema.yaml").unlink()
    output = tmp_path / "release.zip"
    output.write_bytes(b"previous")
    with pytest.raises(ValueError, match="missing"):
        module.build_archive(root, output)
    assert output.read_bytes() == b"previous"


def test_symlink_input_rejected(tmp_path):
    module = builder()
    root = fixture_root(tmp_path, module)
    path = root / "orm/schema.yaml"
    path.unlink()
    path.symlink_to(ROOT / "orm/schema.yaml")
    with pytest.raises(ValueError, match="symlink"):
        module.build_archive(root, tmp_path / "release.zip")
