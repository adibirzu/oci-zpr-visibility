#!/usr/bin/env python3
"""Deploy the ZPR dashboard to OCI Log Analytics (Management Dashboard import).

Builds an OCI Management Dashboard with embedded saved searches from the
enriched dashboard descriptor (oci_zpr_visibility/dashboard.py) and imports it
via DashxApisClient.import_dashboard. Existing same-name dashboards block import
until an explicit owned-ID migration is available. `--dry-run` prints the plan.

Usage:
  oci-zpr-visibility deploy-dashboard --profile <PROFILE> --region <REGION> [--dry-run]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
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


def import_new_dashboard_suite(md, built: list[dict], compartment_id: str):
    """Create only after complete discovery; names never authorize deletion.

    This deliberately refuses reruns against existing content. Exact-ID owned
    updates and cleanup require a separately verified ownership manifest.
    """
    names = {item["displayName"] for item in built}
    page = None
    seen = set()
    while True:
        kwargs = {"compartment_id": compartment_id}
        if page:
            kwargs["page"] = page
        response = md.list_management_dashboards(**kwargs)
        if any(item.display_name in names for item in response.data.items):
            raise ValueError("existing dashboard name conflicts; explicit owned-ID migration required")
        page = response.headers.get("opc-next-page")
        if not page:
            break
        if page in seen:
            raise ValueError("dashboard inventory pagination did not progress")
        seen.add(page)
    details = oci.management_dashboard.models.ManagementDashboardImportDetails(dashboards=built)
    return md.import_dashboard(details)


def dashboard_inventory(md, compartment):
    items, page, seen = [], None, set()
    while True:
        response = md.list_management_dashboards(compartment_id=compartment,
            **({"page": page} if page else {}))
        items.extend(response.data.items)
        page = response.headers.get("opc-next-page")
        if not page:
            return items
        if page in seen:
            raise ValueError("dashboard inventory pagination did not progress")
        seen.add(page)


def reconcile_owned_dashboards(md, built, compartment, journal, *, inventory=None):
    """Import/update exact owned IDs; journal intent precedes creation.

    Foreign collisions block the entire suite. A timed-out import can be
    reconciled only using both persisted creation intent and installation tags.
    Never delete an old dashboard to perform an upgrade.
    """
    inventory = inventory or (lambda: dashboard_inventory(md, compartment))
    found = inventory()
    plans = []
    for original in built:
        item = copy.deepcopy(original)
        name = item["displayName"]
        entry = journal.get("dashboard", name)
        matches = [d for d in found if d.display_name == name]
        if len(matches) > 1:
            raise ValueError("ambiguous dashboard inventory")
        existing = matches[0] if matches else None
        if existing and (not entry or not entry["created"] or
            existing.compartment_id != compartment or
            (existing.freeform_tags or {}).get("zpr-installation") != journal.installation or
            entry["identity"] not in (None, existing.dashboard_id)):
            raise ValueError("foreign dashboard collision")
        if entry and entry["identity"] and not existing:
            raise ValueError("owned dashboard missing; explicit recovery required")
        revision = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
        item["freeformTags"] = {**item.get("freeformTags", {}),
            "zpr-installation": journal.installation, "zpr-revision": revision}
        # Search IDs must not collide across installations or logical views.
        search_map = {}
        for search in item.get("savedSearches", []):
            previous = search["id"]
            search["id"] = f"{journal.installation}-{_slug(name)}-{previous}"
            search["freeformTags"] = {**search.get("freeformTags", {}),
                                      "zpr-installation": journal.installation}
            search_map[previous] = search["id"]
        for tile in item.get("tiles", []):
            tile["savedSearchId"] = search_map[tile["savedSearchId"]]
        etag = None
        if existing:
            response = md.get_management_dashboard(existing.dashboard_id)
            actual = response.data
            if actual.compartment_id != compartment or (actual.freeform_tags or {}).get("zpr-installation") != journal.installation:
                raise ValueError("dashboard ownership changed")
            etag = response.headers["etag"]
            item["dashboardId"] = existing.dashboard_id
        else:
            item["dashboardId"] = f"{journal.installation}-{_slug(name)}"
        plans.append((item, existing, etag, revision))
    for item, existing, etag, revision in plans:
        name = item["displayName"]
        if existing:
            journal.record("dashboard", name, existing.dashboard_id, created=True,
                           revision=(existing.freeform_tags or {}).get("zpr-revision"))
            if (existing.freeform_tags or {}).get("zpr-revision") == revision:
                searches = getattr(md.get_management_dashboard(existing.dashboard_id).data, "saved_searches", None) or []
                for search in searches:
                    if search.compartment_id != compartment or (search.freeform_tags or {}).get("zpr-installation") != journal.installation:
                        raise ValueError("saved search ownership missing")
                    journal.record("saved_search", search.id, search.id, created=True)
                continue
        else:
            journal.record("dashboard", name, None, created=True)
        md.import_dashboard(oci.management_dashboard.models.ManagementDashboardImportDetails(
            dashboards=[item]), **({"if_match": etag} if etag else {}))
        matches = [d for d in inventory() if d.display_name == name and
            d.compartment_id == compartment and
            (d.freeform_tags or {}).get("zpr-installation") == journal.installation]
        if len(matches) != 1:
            raise ValueError("import identity not yet resolvable; retry bootstrap")
        journal.record("dashboard", name, matches[0].dashboard_id, created=True, revision=revision)
        searches = getattr(md.get_management_dashboard(matches[0].dashboard_id).data, "saved_searches", None) or []
        for search in searches:
            if search.compartment_id != compartment or (search.freeform_tags or {}).get("zpr-installation") != journal.installation:
                raise ValueError("saved search ownership missing")
            journal.record("saved_search", search.id, search.id, created=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="oci-zpr-visibility deploy-dashboard")
    p.add_argument("--auth", choices=["api_key", "instance_principal", "resource_principal"], default="api_key")
    p.add_argument("--config-file", default=None)
    p.add_argument("--profile", default="DEFAULT")
    p.add_argument("--region", default=None)
    p.add_argument("--compartment-id", default=None, help="defaults to the tenancy OCID")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--installation-id")
    p.add_argument("--state-bucket")
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
    if args.installation_id:
        from .ownership import validate_installation
        validate_installation(args.installation_id)
        for item in built:
            item["displayName"] += f" [{args.installation_id}]"
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
    try:
        if args.installation_id:
            if not args.state_bucket or not args.compartment_id:
                raise ValueError("owned deployment requires state bucket and compartment")
            from .ownership import Ownership
            journal = Ownership(session, args.state_bucket, args.installation_id, compartment_id)
            reconcile_owned_dashboards(md, built, compartment_id, journal)
        else:
            import_new_dashboard_suite(md, built, compartment_id)
    except (oci.exceptions.ServiceError, ValueError) as exc:
        print(f"dashboard import blocked: {describe_exception(exc)}", file=sys.stderr)
        return 2
    if not args.quiet:
        print(f"imported dashboard suite: {len(built)} dashboards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
