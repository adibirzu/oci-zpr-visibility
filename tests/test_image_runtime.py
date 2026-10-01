"""Marketplace image delegates to the tested common controller runtime."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("image_runtime", Path(__file__).parents[1] / "image/runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def test_image_runtime_delegates_bootstrap_and_readiness(monkeypatch):
    from oci_zpr_visibility import controller_runtime
    monkeypatch.setattr(runtime.sys, "argv", ["runtime", "bootstrap"])
    with patch.object(controller_runtime, "main", return_value=0) as main:
        assert runtime.main() == 0
    main.assert_called_once_with(["bootstrap"])


def test_image_runtime_delegates_refresh(monkeypatch):
    from oci_zpr_visibility import controller_runtime
    monkeypatch.setattr(runtime.sys, "argv", ["runtime", "refresh"])
    with patch.object(controller_runtime, "main", return_value=0) as main:
        assert runtime.main() == 0
    main.assert_called_once_with(["refresh"])


def test_image_install_removes_build_identity_and_disables_password_ssh():
    root = Path(__file__).parents[1]
    installer = (root / "image/install.sh").read_text()
    firstboot = (root / "image/zpr-firstboot.service").read_text()
    assert "PermitRootLogin no" in installer
    assert "PasswordAuthentication no" in installer
    assert "KbdInteractiveAuthentication no" in installer
    assert 'sshd -T | awk' in installer
    assert "rm -f /etc/ssh/ssh_host_*" in installer
    assert ": >/etc/machine-id" in installer
    assert "ConditionFirstBoot=yes" in firstboot
    assert "ssh-keygen -A" in firstboot
