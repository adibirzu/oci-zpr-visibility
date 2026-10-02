import json
from pathlib import Path
from unittest.mock import patch

import pytest

from oci_zpr_visibility import controller_runtime as runtime


def cfg():
    return {"region": "region", "compartment_id": "scope", "installation_id": "test-install",
        "state_bucket": "bucket", "log_group_name": "group", "flow_log_group_id": "flowgroup", "flow_log_id": "flow"}


def test_runtime_rejects_unknown_config_and_incomplete_flow_pair(tmp_path):
    path = tmp_path / "config.json"
    for config in ({**cfg(), "extra": "bad"}, {**cfg(), "flow_log_id": ""}):
        path.write_text(json.dumps(config))
        with pytest.raises(ValueError):
            runtime.read_config(path)


def test_bootstrap_requires_current_run_queries_after_owned_provisioning(monkeypatch):
    monkeypatch.setenv("OCI_ZPR_SOURCE_NAME", "fixture")
    result = {"run_id": "fresh-run", "flows": 5, "uploaded": 35}
    def refresh(args):
        assert "--collection-compartment-id" in args
        assert "--upload-only" in args and "--strict" in args
        print(json.dumps(result))
        return 0
    with patch("oci_zpr_visibility.provision_la.main", return_value=0) as provision, patch("oci_zpr_visibility.deploy_dashboard.main", return_value=0) as deploy, patch("oci_zpr_visibility.refresh.main", side_effect=refresh), patch("oci_zpr_visibility.validate_dashboards.main", return_value=0) as validate:
        assert runtime.run(cfg(), "bootstrap") == result
    assert "--installation-id" in deploy.call_args.args[0]
    assert "--compartment-id" in provision.call_args.args[0]
    assert "fresh-run" in validate.call_args.args[0]
    assert "35" in validate.call_args.args[0]


def test_readiness_failure_is_bounded_and_status_reports_failure(tmp_path):
    config, status = tmp_path / "config.json", tmp_path / "status.json"
    config.write_text(json.dumps(cfg()))
    with patch.object(runtime, "run", side_effect=RuntimeError("not indexed")):
        with pytest.raises(RuntimeError):
            runtime.main(["bootstrap", "--config", str(config), "--status", str(status)])
    assert not json.loads(status.read_text())["ready"]
    assert "not indexed" not in status.read_text()
