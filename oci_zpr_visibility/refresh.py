#!/usr/bin/env python3
"""Scheduled refresh: collect -> drift -> provision/upload to Log Analytics.

The single schedulable unit (cron / OCI Functions / OKE CronJob). Persists the
run's policy records to Object Storage so the next run can detect statement_hash
drift, then ingests inventory + findings + drift into the LA custom source.

Usage:
  oci-zpr-visibility refresh --profile cap --region eu-frankfurt-1 \
      --state-bucket zpr-visibility-state
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from . import provision_la
from .collector import ZprCollector
from .findings import generate_findings
from .jsonutil import write_jsonl
from .logutil import emit
from .oci_clients import build_session
from .state import compute_drift, load_previous_records, save_records


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="oci-zpr-visibility refresh")
    p.add_argument("--auth", choices=["api_key", "instance_principal", "resource_principal"], default="api_key")
    p.add_argument("--config-file", default=None)
    p.add_argument("--profile", default="cap")
    p.add_argument("--region", default="eu-frankfurt-1")
    p.add_argument("--state-bucket", required=True, help="Object Storage bucket holding previous-run state")
    p.add_argument("--log-group-name", default="zpr-visibility-la")
    p.add_argument("--skip-resources", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    session = build_session(args.auth, args.config_file, args.profile, args.region)
    collector = ZprCollector(session)
    snapshot = collector.collect(include_resources=not args.skip_resources)
    records = collector.records_for_snapshot(snapshot)
    findings = generate_findings(snapshot, [r for r in records if r.get("record_type") == "zpr_policy_statement"])

    previous = load_previous_records(session, args.state_bucket)
    drift = compute_drift(previous, records)
    save_records(session, args.state_bucket, records)

    all_records = [*records, *findings, *drift]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        write_jsonl(Path(fh.name), all_records)
        records_path = fh.name

    rc = provision_la.main([
        "--profile", args.profile, "--region", args.region,
        "--log-group-name", args.log_group_name, "--upload", records_path,
    ])

    published = 0
    try:
        from .metrics import publish_metrics
        published = publish_metrics(session, all_records)
    except Exception as exc:  # noqa: BLE001 - metrics are best-effort
        print(f"WARN: metric publish failed: {getattr(exc, 'message', exc)}", file=sys.stderr)

    emit(
        {"records": len(records), "findings": len(findings), "drift": len(drift),
         "uploaded": len(all_records), "metrics_published": published, "provision_rc": rc},
        f"refresh: {len(records)} records, {len(findings)} findings, {len(drift)} drift -> "
        f"uploaded {len(all_records)}, {published} metrics (provision rc={rc})",
        args.json,
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
