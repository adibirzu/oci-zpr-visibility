#!/usr/bin/env python3
"""Deploy the ZPR dashboard to OCI Log Analytics (Management Dashboard import).

Builds an OCI Management Dashboard with embedded saved searches from the
enriched dashboard descriptor (oci_zpr_visibility/dashboard.py) and imports it
idempotently via DashxApisClient.import_dashboard. `--dry-run` prints the plan.

Usage:
  oci-zpr-visibility deploy-dashboard --profile <PROFILE> --region <REGION> [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys

import oci

from . import dashboard as dash_mod
from .logutil import describe_exception

DISPLAY_NAME = "OCI ZPR Visibility"
DASHBOARD_ID = "oci-zpr-visibility"
# OCI LA's own relative-time token (NOT ISO-8601 "P30D"); the ISO form makes the
# JET time binding fail. The collector re-emits a full snapshot every run, so a
# wide default would multiply raw-record table rows; count widgets are made
# window-independent via two-stage `stats` dedup, and the default window is kept
# narrow so the raw-record tables show roughly the latest snapshot.
DEFAULT_TIME_PERIOD = {"timePeriod": "l60m"}

# Per-visualization options modelled on a working OCI LA dashboard export.
# An EMPTY visualizationOptions object breaks JET viz binding ("reading
# 'length'"); every viz type needs real keys. Unknown types fall back to a
# safe legend+tooltip pair.
_BAR_OPTS = {"legend": "auto", "showTooltip": True, "stacked": True}
_FLAT_OPTS = {"legend": "auto", "showTooltip": True}
VIZ_OPTIONS = {
    "bar": _BAR_OPTS,
    "hbar": _BAR_OPTS,
    "sunburst": _FLAT_OPTS,
    "table": _FLAT_OPTS,
    "tile": _FLAT_OPTS,
    "link": _FLAT_OPTS,  # network/relationship graph (source -> destination)
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _scope_filters(compartment_id: str) -> dict:
    """LogGroup-scoped filter object (NOT a list).

    JET requires scopeFilters to be an object with LogGroup/Entity/LogSet
    scopes; a list triggers "Cannot read properties of undefined (reading
    'localName')" and aborts the whole dashboard. Scoping by LogGroup (rooted
    at the compartment, include sub-compartments) is field-agnostic, so it does
    not reintroduce the old "No data" problem that a Compartment-OCID *field*
    filter caused — our records live in a log group under this compartment.
    """
    root = [{"label": "root", "value": compartment_id}]
    return {
        "LogGroup": {
            "flags": {"IncludeSubCompartments": True},
            "type": "LogGroup", "values": root,
        },
        "Entity": {
            "flags": {"IncludeDependents": True, "ScopeCompartmentId": compartment_id},
            "type": "Entity", "values": [],
        },
        "LogSet": {"flags": {}, "type": "LogSet", "values": []},
        "filters": [
            {"flags": {"includeSubCompartments": True}, "type": "LogGroup", "values": root},
            {"flags": {"includeDependents": True, "scopeCompartmentId": compartment_id},
             "type": "Entity", "values": []},
            {"flags": {}, "type": "LogSet", "values": []},
        ],
        "isGlobal": False,
    }


def _saved_search(search_id, widget, compartment_id) -> dict:
    vt = widget["visualization_type"]
    ui = {
        "enableWidgetInApp": True,
        "queryString": widget["query"],
        "scopeFilters": _scope_filters(compartment_id),
        "showTitle": True,
        "timeSelection": DEFAULT_TIME_PERIOD,
        "visualizationOptions": dict(VIZ_OPTIONS.get(vt, _FLAT_OPTS)),
        "visualizationType": vt,
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


def build_management_dashboard(
    dash: dict,
    compartment_id: str,
    display_name: str = DISPLAY_NAME,
    *,
    tab: dict | None = None,
) -> dict:
    """Pure builder: dashboard descriptor -> Management Dashboard import JSON."""
    widgets = list(tab.get("widgets", [])) if tab else dash_mod.iter_widgets(dash)
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
            "parametersMap": {
                "log-analytics-entity": "$(dashboard.params.log-analytics-entity-filter)",
                "log-analytics-log-group-compartment": "$(dashboard.params.log-analytics-loggroup-filter)",
                "time": "$(dashboard.params.time)",
            },
        })
        saved.append(_saved_search(sid, w, compartment_id))
    return {
        "dashboardId": DASHBOARD_ID if tab is None else f"{DASHBOARD_ID}-{_slug(tab['name'])}",
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
        "uiConfig": {"isFilteringEnabled": True, "isRefreshEnabled": True, "defaultQueryMode": "raw"},
        "dataConfig": [],
        "screenImage": " ",
        "freeformTags": {"platform": "oci-zpr-visibility"},
        "parametersConfig": [
            {"paramName": "log-analytics-loggroup-filter", "displayName": "Log Group Compartment",
             "paramType": "LogAnalyticsLogGroupCompartment", "defaultValue": compartment_id, "isRequired": False},
            {"paramName": "log-analytics-entity-filter", "displayName": "Entity",
             "paramType": "LogAnalyticsEntity", "defaultValue": "", "isRequired": False},
            {"paramName": "time", "displayName": "Time Range", "paramType": "Time",
             "defaultValue": "l60m", "isRequired": False},
        ],
        "tiles": tiles,
        "savedSearches": saved,
    }


def build_management_dashboards(dash: dict, compartment_id: str) -> list[dict]:
    """Build one focused OCI dashboard per logical visibility view."""
    built: list[dict] = []
    for index, tab in enumerate(dash.get("tabs", [])):
        display_name = DISPLAY_NAME if index == 0 else f"{DISPLAY_NAME} - {tab['name']}"
        built.append(
            build_management_dashboard(
                dash,
                compartment_id,
                display_name=display_name,
                tab=tab,
            )
        )
    return built


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="oci-zpr-visibility deploy-dashboard")
    p.add_argument("--auth", choices=["api_key", "instance_principal", "resource_principal"], default="api_key")
    p.add_argument("--config-file", default=None)
    p.add_argument("--profile", default="DEFAULT")
    p.add_argument("--region", default=None)
    p.add_argument("--compartment-id", default=None, help="defaults to the tenancy OCID")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--quiet", action="store_true", help="suppress target identifiers from output")
    args = p.parse_args(argv)

    from .oci_clients import build_session, client
    session = build_session(args.auth, args.config_file, args.profile, args.region)
    compartment_id = args.compartment_id or session.tenancy_id

    dash = dash_mod.load_dashboard()
    errors = dash_mod.validate_dashboard(dash)
    if errors:
        print("dashboard descriptor invalid:", *errors, sep="\n  ", file=sys.stderr)
        return 2
    built = build_management_dashboards(dash, compartment_id)
    if not args.quiet:
        print(f"dashboard suite: {len(built)} focused dashboards / "
              f"{sum(len(item['tiles']) for item in built)} tiles")

    if args.dry_run:
        if not args.quiet:
            for item in built:
                print(f"  {item['displayName']}: {len(item['tiles'])} tiles")
            print("dry-run: not imported")
        return 0

    md = client(session, "management_dashboard.DashxApisClient")
    # idempotent: delete any existing same-name dashboard first
    try:
        for item in built:
            for d in md.list_management_dashboards(
                compartment_id=compartment_id, display_name=item["displayName"]
            ).data.items:
                md.delete_management_dashboard(d.dashboard_id)
                if not args.quiet:
                    print(f"  replaced existing dashboard: {item['displayName']}")
    except oci.exceptions.ServiceError as exc:
        if not args.quiet:
            print(f"  (list/delete skipped: {describe_exception(exc)})")
    details = oci.management_dashboard.models.ManagementDashboardImportDetails(dashboards=built)
    md.import_dashboard(details)
    if not args.quiet:
        print(f"imported dashboard suite: {len(built)} dashboards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
