#!/usr/bin/env python3
"""Run every ZPR dashboard query against live OCI Log Analytics and report
DATA / ZERO_ALLOWED / NOT_APPLICABLE / ZERO / ERROR per widget.

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
import os
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

SOURCE_FILTER = f"'Log Source' = '{os.environ.get('OCI_ZPR_SOURCE_NAME', 'OCI ZPR Visibility JSON')}'"
# A run that reports any status other than NOT_CONFIGURED proves flow collection
# was wired up, so flow-dependent widgets must produce data.
FLOW_RUNS_QUERY = (
    f"{SOURCE_FILTER} | where record_type = 'zpr_run' "
    f"and flow_collection_status != '{FLOW_STATUS_NOT_CONFIGURED}' "
    "| fields run_id, flow_collection_status"
)


def _query_scope(m, cfg):
    group = cfg.get("query_log_group")
    return [m.ScopeFilter(field_name="Log Group", values=[group])] if group else None


def _count_rows(la, ns, m, cfg, time_filter, query: str, max_total_count: int = 1) -> int:
    resp = la.query(
        namespace_name=ns,
        query_details=m.QueryDetails(
            compartment_id=cfg.get("query_compartment", cfg["tenancy"]),
            compartment_id_in_subtree=True,
            scope_filters=_query_scope(m, cfg),
            query_string=query,
            sub_system="LOG",
            time_filter=time_filter,
            max_total_count=max_total_count,
            should_run_async=False,
            should_include_total_count=True,
        ),
    )
    return resp.data.total_count if resp.data.total_count is not None else len(resp.data.items or [])


def _widget_status(count: int | None, widget: dict, flow_configured: bool, resource_coverage: dict | None = None) -> str:
    """Classify a widget result.

    Zero rows is a failure by default. Flow-dependent widgets are only exempt
    when the ingested runs say flow collection was never configured — when it
    was configured, a zero row count is still a real gate failure.
    """
    families = widget.get("resource_families", [])
    if families:
        coverage = resource_coverage or {}
        if any(str(coverage.get(f, {}).get("coverage_status", "")).upper() != "COLLECTED" for f in families):
            return "UNAVAILABLE"
        if not count:
            try:
                eligible = sum(int(coverage[f]["eligible_count"]) for f in families)
            except (KeyError, ValueError, TypeError):
                return "UNAVAILABLE"
            return "ZERO_ALLOWED" if eligible == 0 else "ZERO"
    if count:
        return "DATA"
    if widget.get("allow_zero"):
        return "ZERO_ALLOWED"
    if widget.get("data_dependency") == dash_mod.FLOW_DEPENDENCY and not flow_configured:
        return "NOT_APPLICABLE"
    return "ZERO"


def _count_indexed_records(la, ns, m, cfg, time_filter, run_id: str) -> int:
    """Use an exact aggregate, not a capped record-list total/estimate."""
    resp = la.query(
        namespace_name=ns,
        query_details=m.QueryDetails(
            compartment_id=cfg.get("query_compartment", cfg["tenancy"]),
            compartment_id_in_subtree=True,
            query_string=(f"{SOURCE_FILTER} | where run_id = '{run_id}' "
                          "| stats count as indexed_records"),
            sub_system="LOG", time_filter=time_filter,
            max_total_count=1, should_run_async=False,
        ),
    )
    rows = resp.data.items or []
    count = int(rows[0]["indexed_records"]) if rows else 0
    if count < 0:
        raise ValueError("negative indexed record count")
    return count


def main(argv=None) -> int:
    global SOURCE_FILTER, FLOW_RUNS_QUERY
    source = os.environ.get("OCI_ZPR_SOURCE_NAME", "OCI ZPR Visibility JSON")
    if any(c in source for c in "'\n\r"):
        raise ValueError("invalid Log Analytics source name")
    SOURCE_FILTER = f"'Log Source' = '{source}'"
    FLOW_RUNS_QUERY = (f"{SOURCE_FILTER} | where record_type = 'zpr_run' "
        f"and flow_collection_status != '{FLOW_STATUS_NOT_CONFIGURED}' | fields run_id, flow_collection_status")
    p = argparse.ArgumentParser()
    p.add_argument("--profile", default="DEFAULT")
    p.add_argument("--auth", choices=["api_key", "instance_principal", "resource_principal"], default="api_key")
    p.add_argument("--config-file", default=None)
    p.add_argument("--region", default=None)
    p.add_argument("--compartment-id", default=None, help="Log Analytics destination scope; defaults to tenancy, includes its subtree")
    p.add_argument("--log-group-id", default=None, help="Exact expected destination log group OCID")
    p.add_argument("--log-group-name", default="zpr-visibility-la", help="Resolve uniquely in the destination compartment when no ID is supplied")
    p.add_argument("--lookback-minutes", type=int, default=60)
    p.add_argument("--lookback-days", type=int, default=None, help="legacy override for wider evidence audits")
    p.add_argument("--expected-run-id", default=None, help="require records from this fresh collector run")
    p.add_argument("--expected-record-count", type=int, default=None,
                   help="minimum indexed records required for --expected-run-id")
    p.add_argument("--quiet", action="store_true", help="emit only a sanitized summary")
    p.add_argument("--allow-empty-widgets", action="store_true",
                   help="Allow successful empty widget results; exact-run indexing is still required when configured")
    p.add_argument("--json", help="write a JSON report to this path")
    args = p.parse_args(argv)

    try:
        cfg = oci.config.from_file(profile_name=args.profile)
        if args.region:
            # Without --region the profile's own region stands; overwriting it
            # with None would fail validate_config, which requires `region`.
            cfg["region"] = args.region
        oci.config.validate_config(cfg)
        cfg["query_compartment"] = args.compartment_id or cfg["tenancy"]
        la = oci.log_analytics.LogAnalyticsClient(cfg)
        ns = oci.object_storage.ObjectStorageClient(cfg).get_namespace().data
        if args.log_group_id:
            group = la.get_log_analytics_log_group(ns, args.log_group_id).data
            if group.compartment_id != cfg["query_compartment"]:
                raise ValueError("log group does not belong to the expected destination compartment")
            cfg["query_log_group"] = group.id
        else:
            groups = oci.pagination.list_call_get_all_results(
                la.list_log_analytics_log_groups, namespace_name=ns,
                compartment_id=cfg["query_compartment"], limit=200,
            ).data
            matches = [g for g in groups if g.display_name == args.log_group_name]
            if len(matches) != 1:
                raise ValueError("expected exactly one destination log group; provide --compartment-id and --log-group-id")
            cfg["query_log_group"] = matches[0].id
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

    coverage = {}
    coverage_query = (
        f"{SOURCE_FILTER} | where record_type = 'zpr_coverage' "
        "| stats latest(coverage_status) as coverage_status, "
        "latest(eligible_count) as eligible_count by resource_type"
    )
    try:
        response = la.query(namespace_name=ns, limit=100, query_details=m.QueryDetails(
            compartment_id=cfg["query_compartment"], compartment_id_in_subtree=True,
            scope_filters=_query_scope(m, cfg), query_string=coverage_query,
            sub_system="LOG", time_filter=time_filter, max_total_count=100,
            should_run_async=False,
        ))
        coverage = {r["resource_type"]: r for r in response.data.items or []}
    except oci.exceptions.ServiceError:
        pass  # Family views fail unavailable when coverage cannot be established.

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
                        compartment_id=cfg.get("query_compartment", cfg["tenancy"]),
                        compartment_id_in_subtree=True,
                        scope_filters=_query_scope(m, cfg),
                        query_string=q,
                        sub_system="LOG",
                        time_filter=time_filter,
                        max_total_count=50,
                        should_run_async=False,
                        should_include_total_count=True,
                    ),
                )
                count = resp.data.total_count if resp.data.total_count is not None else len(resp.data.items or [])
                status = _widget_status(count, widget, flow_configured, coverage)
            except oci.exceptions.ServiceError as exc:
                count, status = None, "ERROR"
                err = describe_exception(exc)
            else:
                err = None
            results.append({"tab": tab["name"], "widget": widget["name"],
                            "status": status, "count": count, "error": err})
            if not args.quiet:
                mark = {"DATA": "✓", "ZERO_ALLOWED": "·", "NOT_APPLICABLE": "○",
                        "ZERO": "!", "UNAVAILABLE": "?", "ERROR": "✗"}[status]
                print(f"  {mark} [{tab['name'][:18]:18}] {widget['name'][:34]:34} "
                      f"{status:5} rows={count if count is not None else '-'}"
                      + (f"  {err[:60]}" if err else ""))

    current_run_count = None
    freshness_error = None
    if args.expected_run_id:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", args.expected_run_id):
            print("invalid expected run identifier", file=sys.stderr)
            return 3
        try:
            current_run_count = _count_indexed_records(
                la, ns, m, cfg, time_filter, args.expected_run_id
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
        except (KeyError, TypeError, ValueError):
            freshness_error = "invalid indexed record count response"

    from collections import Counter
    tally = Counter(r["status"] for r in results)
    print(f"validated={len(results)} data={tally['DATA']} zero_allowed={tally['ZERO_ALLOWED']} "
          f"not_applicable={tally['NOT_APPLICABLE']} "
          f"zero_unexpected={tally['ZERO']} unavailable={tally['UNAVAILABLE']} "
          f"errors={tally['ERROR']} fresh_run_records={current_run_count if current_run_count is not None else 'not-required'}")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2))
        print(f"report -> {args.json}")

    if tally["ERROR"]:
        return 2
    if tally["ZERO"] or tally["UNAVAILABLE"]:
        return 1
    if freshness_error:
        if not args.quiet:
            print(f"freshness gate failed: {freshness_error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
