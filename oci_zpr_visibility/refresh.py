#!/usr/bin/env python3
"""Scheduled refresh: collect -> drift -> provision/upload to Log Analytics.

The single schedulable unit (cron / OCI Functions / OKE CronJob). Persists the
run's policy records to Object Storage so the next run can detect statement_hash
drift, then ingests inventory + findings + drift into the LA custom source.

Usage:
  oci-zpr-visibility refresh --profile <PROFILE> --region <REGION> \
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
from .logutil import describe_exception, emit
from .oci_clients import build_session
from .state import compute_drift, load_previous_records, save_records
from .schema import (
    FLOW_STATUS_FAILED,
    FLOW_STATUS_NOT_CONFIGURED,
    FLOW_STATUS_SUCCEEDED,
    new_run_id,
    normalize_records,
    run_record,
)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="oci-zpr-visibility refresh")
    p.add_argument("--auth", choices=["api_key", "instance_principal", "resource_principal"], default="api_key")
    p.add_argument("--config-file", default=None)
    p.add_argument("--profile", default="DEFAULT")
    p.add_argument("--region", default=None)
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
    p.add_argument("--quiet", action="store_true", help="suppress target identifiers from command output")
    args = p.parse_args(argv)

    session = build_session(args.auth, args.config_file, args.profile, args.region)
    run_id = new_run_id()
    collector = ZprCollector(session)
    snapshot = collector.collect(include_resources=not args.skip_resources)
    records = collector.records_for_snapshot(snapshot)
    policy_records = [r for r in records if r.get("record_type") == "zpr_policy_statement"]
    findings = generate_findings(snapshot, policy_records)

    # Flow correlation (best-effort): turn VCN Flow Logs into classified
    # zpr_enriched_flow records so the dashboard's traffic KPIs populate. A flow
    # failure must not break inventory/findings ingestion.
    flows: list[dict] = []
    flow_collection_status = FLOW_STATUS_NOT_CONFIGURED
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
            flow_collection_status = FLOW_STATUS_SUCCEEDED
        except Exception as exc:  # noqa: BLE001 - traffic KPIs are best-effort
            flow_collection_status = FLOW_STATUS_FAILED
            if not args.quiet:
                print(f"WARN: flow correlation failed: {describe_exception(exc)}", file=sys.stderr)

    previous = load_previous_records(session, args.state_bucket)
    drift = compute_drift(previous, records)

    snapshot_time = str(snapshot.get("snapshot_time") or "")
    all_records = normalize_records(
        [*records, *findings, *drift, *flows],
        run_id=run_id,
        inventory_snapshot_time=snapshot_time,
    )
    # Gap records are deduplicated; the snapshot carries the true occurrence total.
    collection_error_count = int(
        snapshot.get("collection_error_count") or len(snapshot.get("collection_errors", []))
    )
    all_records.append(
        run_record(
            run_id=run_id,
            event_time=snapshot_time,
            collection_status="SUCCEEDED_WITH_GAPS" if collection_error_count else "SUCCEEDED",
            flow_collection_status=flow_collection_status,
            record_count=len(records),
            finding_count=len(findings),
            drift_count=len(drift),
            flow_count=len(flows),
            collection_error_count=collection_error_count,
        )
    )
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        write_jsonl(Path(fh.name), all_records)
        records_path = fh.name

    prov_argv = ["--auth", args.auth, "--profile", args.profile,
                 "--log-group-name", args.log_group_name, "--upload", records_path]
    if args.region:
        prov_argv += ["--region", args.region]
    if args.config_file:
        prov_argv += ["--config-file", args.config_file]
    if args.quiet:
        prov_argv += ["--quiet"]
    try:
        rc = provision_la.main(prov_argv)
    finally:
        # Records can contain tenant inventory and flow details. The upload
        # staging file is intentionally short-lived and must not remain on disk.
        Path(records_path).unlink(missing_ok=True)
    if rc == 0:
        # Advance drift state only after the current evidence was accepted for
        # upload. A failed upload must not erase the next run's comparison base.
        save_records(session, args.state_bucket, records)

    published = 0
    try:
        from .metrics import publish_metrics
        published = publish_metrics(session, all_records)
    except Exception as exc:  # noqa: BLE001 - metrics are best-effort
        if not args.quiet:
            print(f"WARN: metric publish failed: {describe_exception(exc)}", file=sys.stderr)

    emit(
        {"run_id": run_id, "records": len(records), "findings": len(findings), "drift": len(drift),
         "flows": len(flows), "uploaded": len(all_records), "metrics_published": published,
         "provision_rc": rc},
        f"refresh: {len(records)} records, {len(findings)} findings, {len(drift)} drift, "
        f"{len(flows)} flows -> uploaded {len(all_records)}, {published} metrics (provision rc={rc})",
        args.json,
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
