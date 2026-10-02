import importlib.util
import os
from pathlib import Path
import tarfile
import pytest


def test_archive_is_byte_identical_despite_input_mtimes_and_excludes_caches(tmp_path, monkeypatch):
    script = Path(__file__).parents[1] / "scripts" / "build_collector_archive.py"
    spec = importlib.util.spec_from_file_location("archive_builder", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "source"
    for folder in ("oci_zpr_visibility", "log_analytics"):
        (root / folder).mkdir(parents=True)
    source = root / "oci_zpr_visibility" / "cli.py"
    source.write_text("print('hello')\n")
    (root / "oci_zpr_visibility" / "bad.pyc").write_bytes(b"cache")
    (root / "oci_zpr_visibility" / ".env").write_text("SECRET")
    (root / "log_analytics" / "receipt.json").write_text("SECRET")
    (root / "log_analytics" / "secret.pem").write_text("SECRET")
    (root / "pyproject.toml").write_text("[project]\n")
    (root / "README.md").write_text("test")
    (root / "LICENSE").write_text("Apache-2.0")
    (root / "requirements-runtime.lock").write_text("fixture")
    (root / "requirements-build.lock").write_text("fixture")
    (root / "oci_zpr_visibility/__init__.py").write_text("")
    for name in module.DESCRIPTORS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    first, second = tmp_path / "one.tgz", tmp_path / "two.tgz"
    module.build_archive(root, first)
    os.utime(source, (100, 100))
    module.build_archive(root, second)
    assert first.read_bytes() == second.read_bytes()
    assert first.stat().st_mtime == second.stat().st_mtime == 946684800
    with tarfile.open(first) as archive:
        assert archive.getnames() == sorted([
            "LICENSE", "README.md", *module.DESCRIPTORS, "oci_zpr_visibility/__init__.py",
            "oci_zpr_visibility/cli.py", "pyproject.toml", "requirements-runtime.lock",
            "requirements-build.lock"])
        assert all(member.mtime == 0 for member in archive.getmembers())
    with monkeypatch.context() as patch:
        def fail_archive(*args, **kwargs):
            raise OSError("simulated build failure")
        patch.setattr(module.tarfile, "open", fail_archive)
        with pytest.raises(OSError, match="simulated"):
            module.build_archive(root, first)
    assert first.read_bytes() == second.read_bytes()
    source.unlink()
    (root / "README.md").unlink()
    with pytest.raises(ValueError, match="missing"):
        module.build_archive(root, first)
    assert first.read_bytes() == second.read_bytes()
