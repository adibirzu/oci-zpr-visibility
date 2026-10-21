import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest


spec = importlib.util.spec_from_file_location("rm_lifecycle", Path(__file__).parents[1] / "orm/rm_lifecycle.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def cfg():
    return {"namespace": "namespace", "state_bucket": "bucket", "installation": "test-install",
        "region": "region", "compartment": "scope", "instance": "controller",
        "attribute_namespace": "shared-namespace", "attribute_name": "owned-attribute",
        "attribute_description": "owned-description"}


def test_live_ownership_mismatch_stops_before_guest_command():
    runner = module.Lifecycle(cfg())
    runner.cli = Mock(return_value={"data": {"compartment-id": "foreign", "freeform-tags": {}}})
    runner.guest = Mock()
    with pytest.raises(ValueError, match="ownership"):
        runner.wait()
    runner.guest.assert_not_called()


def test_destroy_rejects_unowned_bucket_objects():
    runner = module.Lifecycle(cfg())
    runner.verify = Mock()
    runner.cli = Mock(return_value={"data": {"objects": [{"name": "foreign-data"}]}})
    runner.guest = Mock()
    with pytest.raises(ValueError, match="unowned"):
        runner.destroy()
    assert runner.cli.call_count == 1
    runner.guest.assert_not_called()


def test_destroy_requires_cleanup_receipt_before_purge():
    runner = module.Lifecycle(cfg())
    runner.verify = Mock()
    runner.verify_attribute = Mock()
    runner.guest = Mock(return_value={})
    runner.cli = Mock(side_effect=[{"data": {"objects": [{"name": "zpr-visibility/ownership.json"}]}},
        json.dumps({"target": {"installation": "test-install", "compartment": "scope", "region": "region"}, "cleanup_complete": False})])
    with pytest.raises(ValueError, match="not confirmed"):
        runner.destroy()
    assert runner.cli.call_count == 2


def test_destroy_without_manifest_preserves_existing_state():
    runner = module.Lifecycle(cfg())
    runner.verify = Mock()
    runner.verify_attribute = Mock()
    runner.cli = Mock(return_value={"data": [{"name": "zpr-visibility/previous_records.jsonl"}]})
    with pytest.raises(ValueError, match="migration"):
        runner.destroy()
    assert runner.cli.call_count == 1


def test_guest_operation_allowlist():
    runner = module.Lifecycle(cfg())
    runner.cli = Mock()
    with pytest.raises(ValueError):
        runner.guest("shell")
    runner.cli.assert_not_called()


def test_orm_has_no_job_side_external_auth_or_local_exec_hooks():
    root = Path(__file__).parents[1] / "orm"
    assert not (root / "lifecycle.tf").exists()
    terraform = "\n".join(path.read_text() for path in root.glob("*.tf"))
    assert "data \"external\"" not in terraform
    assert "local-exec" not in terraform
    assert "hashicorp/external" not in (root / "versions.tf").read_text()


def test_lifecycle_cli_uses_explicit_operator_profile(monkeypatch):
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        return Mock(returncode=0, stdout='{"data": {}}', stderr="")
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module.Lifecycle(cfg()).cli("os", "ns", "get")
    assert calls[0][:3] == ["oci", "--profile", "DEFAULT"]
