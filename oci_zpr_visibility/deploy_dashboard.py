#!/usr/bin/env python3
"""Deploy the ZPR dashboard to OCI Log Analytics (Management Dashboard import).

Builds an OCI Management Dashboard with embedded saved searches from the
enriched dashboard descriptor (oci_zpr_visibility/dashboard.py) and imports it
idempotently via DashxApisClient.import_dashboard. `--dry-run` prints the plan.

Usage:
  oci-zpr-visibility deploy-dashboard --profile cap --region eu-frankfurt-1 [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys

import oci

from . import dashboard as dash_mod

DISPLAY_NAME = "OCI ZPR Visibility"
DASHBOARD_ID = "oci-zpr-visibility"
DEFAULT_TIME_PERIOD = {"timePeriod": "P30D"}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _scope_filters(compartment_id: str) -> list[dict]:
    return [{
        "field": "Compartment OCID",
        "fieldname": "Compartment OCID",
        "isAdvanced": False,
        "values": [compartment_id],
    }]


def _saved_search(search_id, widget, compartment_id) -> dict:
    ui = {
        "enableWidgetInApp": True,
        "queryString": widget["query"],
        "scopeFilters": _scope_filters(compartment_id),
        "showTitle": True,
        "timeSelection": DEFAULT_TIME_PERIOD,
        "visualizationOptions": widget.get("visualization_options", {}),
        "visualizationType": widget["visualization_type"],
        "vizType": "lxSavedSearchWidgetType",
    }
    tags = {}
    if widget.get("ask_ai_prompts"):
        import json
        tags["ask_ai_prompts"] = json.dumps(widget["ask_ai_prompts"])
    return {
        "id": search_id,
        "displayName": widget["name"],
        "providerId": "log-analytics",
        "providerName": "Log Analytics",
        "providerVersion": "3.0.0",
        "compartmentId": compartment_id,
        "isOobSavedSearch": False,
        "description": widget.get("description", ""),
        "nls": {},
        "type": "SEARCH_SHOW_IN_DASHBOARD",
        "uiConfig": ui,
        "dataConfig": [],
        "screenImage": " ",
        "metadataVersion": "2.0",
        "widgetTemplate": "visualizations/chartWidgetTemplate.html",
        "widgetVM": "jet-modules/dashboards/widgets/lxSavedSearchWidget",
        "freeformTags": tags,
        "parametersConfig": [],
    }


def build_management_dashboard(dash: dict, compartment_id: str, display_name: str = DISPLAY_NAME) -> dict:
    """Pure builder: dashboard descriptor -> Management Dashboard import JSON."""
    widgets = dash_mod.iter_widgets(dash)
    placed = {p["name"]: p for p in dash_mod.resolve_layout(widgets)}
    tiles, saved = [], []
    seen: dict[str, int] = {}
    for w in widgets:
        sid = _slug(w["name"])
        seen[sid] = seen.get(sid, 0) + 1
        if seen[sid] > 1:
            sid = f"{sid}-{seen[sid]}"
        p = placed[w["name"]]
        tiles.append({
            "displayName": w["name"],
            "savedSearchId": sid,
            "row": p["row"], "column": p["column"],
            "width": p["width"], "height": p["height"],
            "nls": {}, "uiConfig": {}, "dataConfig": [],
            "state": "DEFAULT", "drilldownConfig": [],
        })
        saved.append(_saved_search(sid, w, compartment_id))
    return {
        "dashboardId": DASHBOARD_ID,
        "providerId": "log-analytics",
        "providerName": "Log Analytics",
        "providerVersion": "3.0.0",
        "displayName": display_name,
        "description": dash.get("description", "OCI ZPR visibility posture, policy, traffic, and governance."),
        "compartmentId": compartment_id,
        "isOobDashboard": False,
        "isShowInHome": True,
        "isShowDescription": True,
        "metadataVersion": "2.0",
        "type": "normal",
        "isFavorite": False,
        "nls": {},
        "uiConfig": {"isFilteringEnabled": True, "isRefreshEnabled": True},
        "dataConfig": [],
        "screenImage": " ",
        "freeformTags": {"platform": "oci-zpr-visibility"},
        "parametersConfig": [
            {"paramName": "time", "displayName": "Time Range", "paramType": "Time",
             "defaultValue": "P30D", "isRequired": False},
        ],
        "tiles": tiles,
        "savedSearches": saved,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="oci-zpr-visibility deploy-dashboard")
    p.add_argument("--profile", default="cap")
    p.add_argument("--region", default="eu-frankfurt-1")
    p.add_argument("--compartment-id", default=None, help="defaults to the tenancy OCID")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    cfg = oci.config.from_file(profile_name=args.profile)
    cfg["region"] = args.region
    oci.config.validate_config(cfg)
    compartment_id = args.compartment_id or cfg["tenancy"]

    dash = dash_mod.load_dashboard()
    errors = dash_mod.validate_dashboard(dash)
    if errors:
        print("dashboard descriptor invalid:", *errors, sep="\n  ", file=sys.stderr)
        return 2
    built = build_management_dashboard(dash, compartment_id)
    print(f"dashboard '{built['displayName']}': {len(built['tiles'])} tiles / "
          f"{len(built['savedSearches'])} saved searches")

    if args.dry_run:
        for t in built["tiles"]:
            print(f"  tile {t['row']},{t['column']} {t['width']}x{t['height']}  {t['displayName']}")
        print("dry-run: not imported")
        return 0

    md = oci.management_dashboard.DashxApisClient(cfg)
    # idempotent: delete any existing same-name dashboard first
    try:
        for d in md.list_management_dashboards(compartment_id=compartment_id, display_name=built["displayName"]).data.items:
            md.delete_management_dashboard(d.dashboard_id)
            print(f"  deleted existing dashboard {d.dashboard_id}")
    except oci.exceptions.ServiceError as exc:
        print(f"  (list/delete skipped: {getattr(exc, 'message', exc)})")
    details = oci.management_dashboard.models.ManagementDashboardImportDetails(dashboards=[built])
    md.import_dashboard(details)
    print(f"imported dashboard: {built['displayName']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
