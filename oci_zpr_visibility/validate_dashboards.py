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

from . import dashboard as dash_mod
from .logutil import describe_exception
from .schema import FLOW_STATUS_NOT_CONFIGURED

PROJECT_DIR = Path(__file__).resolve().parent.parent
DASHBOARD = PROJECT_DIR / "log_analytics" / "dashboards" / "oci_zpr_visibility_dashboard.json"

SOURCE_FILTER = "'Log Source' = 'OCI ZPR Visibility JSON'"
# A run that reports any status other than NOT_CONFIGURED proves flow collection
# was wired up, so flow-dependent widgets must produce data.
FLOW_RUNS_QUERY = (
    f"{SOURCE_FILTER} | where record_type = 'zpr_run' "
    f"and flow_collection_status != '{FLOW_STATUS_NOT_CONFIGURED}' "
    "| fields run_id, flow_collection_status"
)


def _count_rows(la, ns, m, cfg, time_filter, query: str, max_total_count: int = 1) -> int:
    resp = la.query(
        namespace_name=ns,
        query_details=m.QueryDetails(
            compartment_id=cfg["tenancy"],
            query_string=query,
            sub_system="LOG",
            time_filter=time_filter,
            max_total_count=max_total_count,
            should_run_async=False,
            should_include_total_count=True,
        ),
    )
    return resp.data.total_count if resp.data.total_count is not None else len(resp.data.items or [])


def _widget_status(count: int | None, widget: dict, flow_configured: bool) -> str:
    """Classify a widget result.

    Zero rows is a failure by default. Flow-dependent widgets are only exempt
    when the ingested runs say flow collection was never configured — when it
    was configured, a zero row count is still a real gate failure.
    """
    if count:
        return "DATA"
    if widget.get("allow_zero"):
        return "ZERO_ALLOWED"
    if widget.get("data_dependency") == dash_mod.FLOW_DEPENDENCY and not flow_configured:
        return "NOT_APPLICABLE"
    return "ZERO"


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
        if args.region:
            # Without --region the profile's own region stands; overwriting it
            # with None would fail validate_config, which requires `region`.
            cfg["region"] = args.region
        oci.config.validate_config(cfg)
        la = oci.log_analytics.LogAnalyticsClient(cfg)
        ns = oci.object_storage.ObjectStorageClient(cfg).get_namespace().data
    except Exception as exc:  # noqa: BLE001
        print(f"OCI setup failed: {describe_exception(exc)}", file=sys.stderr)
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

    dash = dash_mod.load_dashboard()
    schema_errors = dash_mod.validate_dashboard(dash)
    if schema_errors:
        print("dashboard schema errors:", *schema_errors, sep="\n  ", file=sys.stderr)
        return 2

    try:
        flow_configured = _count_rows(la, ns, m, cfg, time_filter, FLOW_RUNS_QUERY) > 0
    except oci.exceptions.ServiceError:
        # Unable to prove flow collection is off, so stay strict.
        flow_configured = True
    if not args.quiet and not flow_configured:
        print("  flow collection not configured in this window: "
              "flow-dependent widgets are reported as NOT_APPLICABLE")

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
                status = _widget_status(count, widget, flow_configured)
            except oci.exceptions.ServiceError as exc:
                count, status = None, "ERROR"
                err = describe_exception(exc)
            else:
                err = None
            results.append({"tab": tab["name"], "widget": widget["name"],
                            "status": status, "count": count, "error": err})
            if not args.quiet:
                mark = {"DATA": "✓", "ZERO_ALLOWED": "·", "NOT_APPLICABLE": "○",
                        "ZERO": "!", "ERROR": "✗"}[status]
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
            f"{SOURCE_FILTER} | where run_id = '{args.expected_run_id}' "
            "| fields record_type, run_id, schema_version"
        )
        try:
            current_run_count = _count_rows(
                la, ns, m, cfg, time_filter, evidence_query, max_total_count=1000
            )
            if current_run_count <= 0:
                freshness_error = "no current-run records in the dashboard time window"
            elif args.expected_record_count is not None and current_run_count < args.expected_record_count:
                freshness_error = (
                    f"current run is still indexing ({current_run_count}/"
                    f"{args.expected_record_count} records)"
                )
        except oci.exceptions.ServiceError as exc:
            freshness_error = describe_exception(exc)

    from collections import Counter
    tally = Counter(r["status"] for r in results)
    print(f"validated={len(results)} data={tally['DATA']} zero_allowed={tally['ZERO_ALLOWED']} "
          f"not_applicable={tally['NOT_APPLICABLE']} "
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
