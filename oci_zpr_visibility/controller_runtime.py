"""Packaged controller workflow. No skill, workstation or GitHub dependency."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import time

from .ownership import validate_installation


def read_config(path):
    cfg = json.loads(Path(path).read_text())
    required = {"region", "compartment_id", "installation_id", "state_bucket",
                "log_group_name", "flow_log_group_id", "flow_log_id"}
    if set(cfg) != required or any(not isinstance(v, str) or
        any(c in v for c in "\n\r\x00") for v in cfg.values()):
        raise ValueError("invalid controller configuration")
    if any(not cfg[key] for key in required - {"flow_log_group_id", "flow_log_id"}):
        raise ValueError("missing controller configuration")
    if bool(cfg["flow_log_group_id"]) != bool(cfg["flow_log_id"]):
        raise ValueError("incomplete flow-log configuration")
    validate_installation(cfg["installation_id"])
    return cfg


def run(cfg, action):
    from .provision_la import owned_source_name
    os.environ["OCI_ZPR_SOURCE_NAME"] = owned_source_name(cfg["installation_id"])
    # Import after the source environment is established.
    from . import deploy_dashboard, provision_la, refresh, validate_dashboards
    auth = ["--auth", "instance_principal", "--region", cfg["region"], "--quiet"]
    owned = ["--installation-id", cfg["installation_id"], "--state-bucket", cfg["state_bucket"]]
    target = ["--compartment-id", cfg["compartment_id"]]
    if action == "bootstrap":
        if provision_la.main([*auth, *owned, *target, "--log-group-name", cfg["log_group_name"]]):
            raise RuntimeError("Log Analytics provisioning failed")
        if deploy_dashboard.main([*auth, *owned, *target]):
            raise RuntimeError("dashboard reconciliation failed")
    args = [*auth, *owned, "--scope-id", cfg["installation_id"],
        "--collection-compartment-id", cfg["compartment_id"], "--log-group-name", cfg["log_group_name"],
        "--log-analytics-compartment-id", cfg["compartment_id"], "--upload-only", "--strict", "--json"]
    if cfg["flow_log_id"]:
        args += ["--flow-log-compartment-id", cfg["compartment_id"],
            "--flow-log-group-id", cfg["flow_log_group_id"], "--flow-log-id", cfg["flow_log_id"]]
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        rc = refresh.main(args)
    result = json.loads(output.getvalue())
    if rc or (cfg["flow_log_id"] and result["flows"] == 0):
        raise RuntimeError("collection incomplete; uploaded partial evidence but not ready")
    # Query/indexing is asynchronous. Retry boundedly without uploading another run.
    for attempt in range(8):
        if not validate_dashboards.main([*auth, *target, "--lookback-minutes", "120",
            "--allow-empty-widgets", "--expected-run-id", result["run_id"], "--expected-record-count", str(result["uploaded"])]):
            return result
        if attempt < 7:
            time.sleep(20)
    raise RuntimeError("current run indexing or dashboard queries did not become ready")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["bootstrap", "refresh"])
    p.add_argument("--config", default="/etc/zpr-visibility/config.json")
    p.add_argument("--status", default="/var/lib/zpr-visibility/status.json")
    args = p.parse_args(argv)
    cfg = read_config(args.config)
    status = Path(args.status)
    status.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = run(cfg, args.action)
    except Exception as exc:
        from .logutil import describe_exception
        status.write_text(json.dumps({"ready": False, "stage": args.action,
                                      "error": describe_exception(exc)}) + "\n")
        raise
    status.write_text(json.dumps({"ready": True, "stage": args.action, **result}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
