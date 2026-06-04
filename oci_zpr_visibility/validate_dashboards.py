#!/usr/bin/env python3
"""Run every ZPR dashboard query against live OCI Log Analytics and report
HIT / MISS / ERROR per widget.

This is the end-to-end gate: it executes (not just parses) each query in
log_analytics/dashboards/oci_zpr_visibility_dashboard.json against the
ingested `OCI ZPR Visibility JSON` source.

Usage:
  .venv/bin/python scripts/validate_dashboards.py --profile cap --region eu-frankfurt-1 [--lookback-days 30]

Exit codes: 0 = all HIT, 1 = some MISS, 2 = some ERROR, 3 = auth/setup failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import oci

PROJECT_DIR = Path(__file__).resolve().parent.parent
DASHBOARD = PROJECT_DIR / "log_analytics" / "dashboards" / "oci_zpr_visibility_dashboard.json"


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", default="cap")
    p.add_argument("--region", default="eu-frankfurt-1")
    p.add_argument("--lookback-days", type=int, default=30)
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
    start = end - timedelta(days=args.lookback_days)
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
                status = "HIT" if count and count > 0 else "MISS"
            except oci.exceptions.ServiceError as exc:
                count, status = None, "ERROR"
                err = getattr(exc, "message", str(exc))
            else:
                err = None
            results.append({"tab": tab["name"], "widget": widget["name"],
                            "status": status, "count": count, "error": err})
            mark = {"HIT": "✓", "MISS": "·", "ERROR": "✗"}[status]
            print(f"  {mark} [{tab['name'][:18]:18}] {widget['name'][:34]:34} "
                  f"{status:5} rows={count if count is not None else '-'}"
                  + (f"  {err[:60]}" if err else ""))

    from collections import Counter
    tally = Counter(r["status"] for r in results)
    print(f"\n=== {tally['HIT']} HIT / {tally['MISS']} MISS / {tally['ERROR']} ERROR "
          f"(of {len(results)} widgets) ===")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2))
        print(f"report -> {args.json}")

    if tally["ERROR"]:
        return 2
    if tally["MISS"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
