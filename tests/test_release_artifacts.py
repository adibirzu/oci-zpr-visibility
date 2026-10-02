import importlib.util
from pathlib import Path
import zipfile

import pytest


ROOT = Path(__file__).parents[1]


def admission(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("release_admission", ROOT / "scripts/check_release_artifacts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def artifacts(tmp_path, monkeypatch):
    module = admission(monkeypatch)
    root = tmp_path / "source"
    (root / "oci_zpr_visibility").mkdir(parents=True)
    (root / "oci_zpr_visibility/__init__.py").write_text("")
    (root / "README.md").write_text("fixture")
    (root / "LICENSE").write_text("Apache-2.0")
    (root / "pyproject.toml").write_text("fixture")
    (root / "requirements-runtime.lock").write_text("fixture")
    (root / "requirements-build.lock").write_text("fixture")
    for name in module.build_collector.__globals__["DESCRIPTORS"]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    for name in module.INPUTS:
        path = root / "orm" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    module.build_collector(root, root / "orm/oci_zpr_visibility_pkg.tgz")
    from build_orm_archive import build_archive
    build_archive(root, root / "orm-stack.zip")
    return root, module


def test_parity_gate_accepts_matching_source(tmp_path, monkeypatch):
    root, module = artifacts(tmp_path, monkeypatch)
    module.check(root)


def test_parity_gate_rejects_stale_collector(tmp_path, monkeypatch):
    root, module = artifacts(tmp_path, monkeypatch)
    (root / "oci_zpr_visibility/__init__.py").write_text("changed")
    with pytest.raises(ValueError, match="ORM artifact differs.*pkg"):
        module.check(root)


def test_parity_gate_rejects_extra_zip_member(tmp_path, monkeypatch):
    root, module = artifacts(tmp_path, monkeypatch)
    with zipfile.ZipFile(root / "orm-stack.zip", "a") as archive:
        archive.writestr("local.tfvars", "DO_NOT_SHIP")
    with pytest.raises(ValueError, match="membership"):
        module.check(root)


def test_parity_gate_rejects_changed_terraform(tmp_path, monkeypatch):
    root, module = artifacts(tmp_path, monkeypatch)
    (root / "orm/controller.tf").write_text("changed")
    with pytest.raises(ValueError, match="ORM artifact differs"):
        module.check(root)


def test_parity_gate_rejects_hidden_zip_metadata(tmp_path, monkeypatch):
    root, module = artifacts(tmp_path, monkeypatch)
    with zipfile.ZipFile(root / "orm-stack.zip", "a") as archive:
        archive.comment = b"PRIVATE_RECEIPT"
    with pytest.raises(ValueError, match="metadata"):
        module.check(root)


def test_parity_gate_needs_no_untracked_collector(tmp_path, monkeypatch):
    root, module = artifacts(tmp_path, monkeypatch)
    (root / "orm/oci_zpr_visibility_pkg.tgz").unlink()
    module.check(root)
