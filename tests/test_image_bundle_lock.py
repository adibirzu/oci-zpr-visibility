import hashlib
import importlib.util
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "build_image_bundle", ROOT / "scripts/build_image_bundle.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def make_wheel(path, name="sample", version="1.0"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}-{version}.dist-info/METADATA",
                         f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
        archive.writestr("sample.py", "x=1\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_wheelhouse_must_match_locked_versions_and_hashes(tmp_path):
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    digest = make_wheel(wheelhouse / "sample-1.0-py3-none-any.whl")
    lock = tmp_path / "requirements.lock"
    lock.write_text(f"sample==1.0 --hash=sha256:{digest}\n")
    module.validate_runtime_wheels(wheelhouse, lock)

    lock.write_text(f"sample==1.0 --hash=sha256:{'0' * 64}\n")
    with pytest.raises(ValueError, match="hash_or_version_mismatch=1"):
        module.validate_runtime_wheels(wheelhouse, lock)


def test_wheelhouse_must_reject_unlocked_packages(tmp_path):
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    digest = make_wheel(wheelhouse / "sample-1.0-py3-none-any.whl")
    make_wheel(wheelhouse / "other-1.0-py3-none-any.whl", "other")
    lock = tmp_path / "requirements.lock"
    lock.write_text(f"sample==1.0 --hash=sha256:{digest}\n")
    with pytest.raises(ValueError, match="extra=1"):
        module.validate_runtime_wheels(wheelhouse, lock)


def test_image_payload_copies_only_allowlisted_assets(tmp_path):
    source, output = tmp_path / "source", tmp_path / "out"
    for name in (*module.DESCRIPTORS, *module.RUNTIME_ASSETS,
                 "image/install.sh", "image/zpr.pkr.hcl", "image/__pycache__/runtime.pyc"):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    module.copy_image_assets(source, output)
    assert (output / module.DESCRIPTORS[0]).is_file()
    assert {p.relative_to(output / "runtime").as_posix()
            for p in (output / "runtime").rglob("*") if p.is_file()} == {
                "runtime.py", "zpr-bootstrap.service", "zpr-bootstrap.timer",
                "zpr-refresh.service", "zpr-refresh.timer",
                "zpr-firstboot.service"}


def test_image_payload_rejects_symlinked_asset(tmp_path):
    source, output = tmp_path / "source", tmp_path / "out"
    target = source / module.DESCRIPTORS[0]
    target.parent.mkdir(parents=True)
    real = tmp_path / "real.json"
    real.write_text("{}")
    target.symlink_to(real)
    with pytest.raises(ValueError, match="symlinks"):
        module.copy_image_assets(source, output)
