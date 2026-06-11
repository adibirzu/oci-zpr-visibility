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
    p.add_argument("--flow-log-group-id", default=None,
                   help="OCI Logging log group OCID holding VCN Flow Logs. When set, refresh "
                        "fetches + correlates flows into zpr_enriched_flow records (traffic KPIs).")
    p.add_argument("--flow-log-id", default=None, help="VCN Flow Log OCID within the flow log group.")
    p.add_argument("--flow-log-compartment-id", default=None,
                   help="Compartment OCID containing the VCN Flow Log. Defaults to the session tenancy.")
    p.add_argument("--flow-lookback-minutes", type=int, default=60,
                   help="How far back to pull flow logs each run (default 60).")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    session = build_session(args.auth, args.config_file, args.profile, args.region)
    collector = ZprCollector(session)
    snapshot = collector.collect(include_resources=not args.skip_resources)
    records = collector.records_for_snapshot(snapshot)
    policy_records = [r for r in records if r.get("record_type") == "zpr_policy_statement"]
    findings = generate_findings(snapshot, policy_records)

    # Flow correlation (best-effort): turn VCN Flow Logs into classified
    # zpr_enriched_flow records so the dashboard's traffic KPIs populate. A flow
    # failure must not break inventory/findings ingestion.
    flows: list[dict] = []
    if args.flow_log_group_id and args.flow_log_id:
        try:
            from datetime import datetime, timedelta, timezone

            from .correlate import correlate_flow_records
            from .flow_logs import fetch_flow_logs
            end = datetime.now(timezone.utc)
            start = end - timedelta(minutes=args.flow_lookback_minutes)
            fmt = "%Y-%m-%dT%H:%M:%S.000Z"
            flow_compartment_id = args.flow_log_compartment_id or session.tenancy_id
            raw_flows = fetch_flow_logs(
                session, flow_compartment_id, args.flow_log_group_id, args.flow_log_id,
                start.strftime(fmt), end.strftime(fmt),
            )
            flows = correlate_flow_records(raw_flows, snapshot, policy_records)
        except Exception as exc:  # noqa: BLE001 - traffic KPIs are best-effort
            print(f"WARN: flow correlation failed: {getattr(exc, 'message', exc)}", file=sys.stderr)

    previous = load_previous_records(session, args.state_bucket)
    drift = compute_drift(previous, records)
    save_records(session, args.state_bucket, records)

    all_records = [*records, *findings, *drift, *flows]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        write_jsonl(Path(fh.name), all_records)
        records_path = fh.name

    prov_argv = ["--auth", args.auth, "--profile", args.profile, "--region", args.region,
                 "--log-group-name", args.log_group_name, "--upload", records_path]
    if args.config_file:
        prov_argv += ["--config-file", args.config_file]
    rc = provision_la.main(prov_argv)

    published = 0
    try:
        from .metrics import publish_metrics
        published = publish_metrics(session, all_records)
    except Exception as exc:  # noqa: BLE001 - metrics are best-effort
        print(f"WARN: metric publish failed: {getattr(exc, 'message', exc)}", file=sys.stderr)

    emit(
        {"records": len(records), "findings": len(findings), "drift": len(drift),
         "flows": len(flows), "uploaded": len(all_records), "metrics_published": published,
         "provision_rc": rc},
        f"refresh: {len(records)} records, {len(findings)} findings, {len(drift)} drift, "
        f"{len(flows)} flows -> uploaded {len(all_records)}, {published} metrics (provision rc={rc})",
        args.json,
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
