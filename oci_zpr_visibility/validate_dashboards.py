#!/usr/bin/env python3
"""Run every ZPR dashboard query against live OCI Log Analytics and report
HIT / MISS / ERROR per widget.

This is the end-to-end gate: it executes (not just parses) each query in
log_analytics/dashboards/oci_zpr_visibility_dashboard.json against the
ingested `OCI ZPR Visibility JSON` source.

Usage:
  .venv/bin/python scripts/validate_dashboards.py --profile <PROFILE> --region <REGION>

Exit codes: 0 = all queries parse/execute and freshness gates pass,
1 = a required freshness/data gate missed, 2 = query error, 3 = auth/setup failure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import oci

PROJECT_DIR = Path(__file__).resolve().parent.parent
DASHBOARD = PROJECT_DIR / "log_analytics" / "dashboards" / "oci_zpr_visibility_dashboard.json"


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", default="DEFAULT")
    p.add_argument("--region", default=None)
    p.add_argument("--lookback-minutes", type=int, default=60)
    p.add_argument("--lookback-days", type=int, default=None, help="legacy override for wider evidence audits")
    p.add_argument("--expected-run-id", default=None, help="require records from this fresh collector run")
    p.add_argument("--expected-record-count", type=int, default=None,
                   help="minimum indexed records required for --expected-run-id")
    p.add_argument("--quiet", action="store_true", help="emit only a sanitized summary")
    p.add_argument("--json", help="write a JSON report to this path")
    args = p.parse_args(argv)

    try:
        cfg = oci.config.from_file(profile_name=args.profile)
        cfg["region"] = args.region
        oci.config.validate_config(cfg)
        la = oci.log_analytics.LogAnalyticsClient(cfg)
        ns = oci.object_storage.ObjectStorageClient(cfg).get_namespace().data
    except Exception as exc:  # noqa: BLE001
        print(f"OCI setup failed: {exc}", file=sys.stderr)
        return 3

    m = oci.log_analytics.models
    end = datetime.now(timezone.utc)
    start = end - (
        timedelta(days=args.lookback_days)
        if args.lookback_days is not None
        else timedelta(minutes=args.lookback_minutes)
    )
    time_filter = m.TimeRange(
        time_start=start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        time_end=end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        time_zone="UTC",
    )

    from . import dashboard as dash_mod
    dash = dash_mod.load_dashboard()
    schema_errors = dash_mod.validate_dashboard(dash)
    if schema_errors:
        print("dashboard schema errors:", *schema_errors, sep="\n  ", file=sys.stderr)
        return 2
    results = []
    for tab in dash["tabs"]:
        for widget in tab["widgets"]:
            q = widget["query"]
            try:
                la.parse_query(
                    namespace_name=ns,
                    parse_query_details=m.ParseQueryDetails(query_string=q, sub_system="LOG"),
                )
                resp = la.query(
                    namespace_name=ns,
                    query_details=m.QueryDetails(
                        compartment_id=cfg["tenancy"],
                        query_string=q,
                        sub_system="LOG",
                        time_filter=time_filter,
                        max_total_count=50,
                        should_run_async=False,
                        should_include_total_count=True,
                    ),
                )
                count = resp.data.total_count if resp.data.total_count is not None else len(resp.data.items or [])
                status = (
                    "DATA" if count and count > 0
                    else "ZERO_ALLOWED" if widget.get("allow_zero")
                    else "ZERO"
                )
            except oci.exceptions.ServiceError as exc:
                count, status = None, "ERROR"
                err = getattr(exc, "message", str(exc))
            else:
                err = None
            results.append({"tab": tab["name"], "widget": widget["name"],
                            "status": status, "count": count, "error": err})
            if not args.quiet:
                mark = {"DATA": "✓", "ZERO_ALLOWED": "·", "ZERO": "!", "ERROR": "✗"}[status]
                print(f"  {mark} [{tab['name'][:18]:18}] {widget['name'][:34]:34} "
                      f"{status:5} rows={count if count is not None else '-'}"
                      + (f"  {err[:60]}" if err else ""))

    current_run_count = None
    freshness_error = None
    if args.expected_run_id:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", args.expected_run_id):
            print("invalid expected run identifier", file=sys.stderr)
            return 3
        evidence_query = (
            f"'Log Source' = 'OCI ZPR Visibility JSON' | where run_id = '{args.expected_run_id}' "
            "| fields record_type, run_id, schema_version"
        )
        try:
            resp = la.query(
                namespace_name=ns,
                query_details=m.QueryDetails(
                    compartment_id=cfg["tenancy"], query_string=evidence_query,
                    sub_system="LOG", time_filter=time_filter, max_total_count=1000,
                    should_run_async=False, should_include_total_count=True,
                ),
            )
            current_run_count = resp.data.total_count or len(resp.data.items or [])
            if current_run_count <= 0:
                freshness_error = "no current-run records in the dashboard time window"
            elif args.expected_record_count is not None and current_run_count < args.expected_record_count:
                freshness_error = (
                    f"current run is still indexing ({current_run_count}/"
                    f"{args.expected_record_count} records)"
                )
        except oci.exceptions.ServiceError as exc:
            freshness_error = exc.__class__.__name__

    from collections import Counter
    tally = Counter(r["status"] for r in results)
    print(f"validated={len(results)} data={tally['DATA']} zero_allowed={tally['ZERO_ALLOWED']} "
          f"zero_unexpected={tally['ZERO']} "
          f"errors={tally['ERROR']} fresh_run_records={current_run_count if current_run_count is not None else 'not-required'}")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2))
        print(f"report -> {args.json}")

    if tally["ERROR"]:
        return 2
    if tally["ZERO"]:
        return 1
    if freshness_error:
        if not args.quiet:
            print(f"freshness gate failed: {freshness_error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
