"""Delete only journal-owned content; shared fields are intentionally preserved."""
import argparse
import json

import oci

from .controller_runtime import read_config
from .oci_clients import build_session, client
from .ownership import Ownership


def owned_response(getter, journal, entry, compartment, *, tagged=True):
    response = getter(entry["identity"])
    item = response.data
    if tagged:
        if item.compartment_id != compartment or (item.freeform_tags or {}).get("zpr-installation") != journal.installation:
            raise ValueError("cleanup ownership verification failed")
    elif item.description != f"ZPR visibility installation={journal.installation}":
        raise ValueError("cleanup content ownership verification failed")
    return response


def cleanup(journal, la, md, compartment, *, execute=False, complete_reference_scan=False):
    plan = []
    preserved = 0
    from .deploy_dashboard import dashboard_inventory
    dashboards = dashboard_inventory(md, compartment)
    # Resolve a timed-out creation only from its journal intent plus live tags.
    for entry in journal.data["resources"].values():
        if entry["kind"] == "log_group" and entry["created"] and not entry["identity"]:
            groups = oci.pagination.list_call_get_all_results(la.list_log_analytics_log_groups,
                namespace_name=journal.ns, compartment_id=compartment, limit=200).data
            matches = [g for g in groups if g.display_name == entry["name"]]
            if len(matches) > 1 or (matches and (matches[0].freeform_tags or {}).get("zpr-installation") != journal.installation):
                raise ValueError("pending log group ownership ambiguous")
            if matches:
                entry["identity"] = matches[0].id
            else:
                entry["deleted"] = True
    owned_dashboards = {e["identity"] for e in journal.data["resources"].values()
        if e["kind"] == "dashboard" and e["created"] and e["identity"] and not e["deleted"]}
    foreign_references = set()
    for dashboard in dashboards:
        if dashboard.dashboard_id not in owned_dashboards:
            actual = md.get_management_dashboard(dashboard.dashboard_id).data
            foreign_references.update(tile.saved_search_id for tile in (actual.tiles or []) if tile.saved_search_id)
    preserved_searches = 0
    for entry in journal.data["resources"].values():
        if entry["kind"] == "field":
            preserved += 1
            continue
        if not entry["created"] or entry["deleted"]:
            continue
        if not entry["identity"]:
            raise ValueError("pending creation must be reconciled before cleanup")
        kind = entry["kind"]
        if kind == "dashboard":
            if not any(d.dashboard_id == entry["identity"] for d in dashboards):
                # Complete authorized inventory proves a previously deleted ID absent.
                entry["deleted"] = True
                continue
            response = owned_response(md.get_management_dashboard, journal, entry, compartment)
            delete = lambda e=entry, r=response: md.delete_management_dashboard(e["identity"], if_match=r.headers["etag"])
        elif kind == "saved_search":
            # A local-compartment dashboard listing cannot prove that another
            # compartment does not reference this shared search. Fail closed.
            if not complete_reference_scan or entry["identity"] in foreign_references:
                preserved_searches += 1
                continue
            try:
                response = owned_response(md.get_management_saved_search, journal, entry, compartment)
            except oci.exceptions.ServiceError as exc:
                if exc.status != 404:
                    raise
                list_searches = getattr(md, "list_management_saved_searches", None)
                if list_searches is None:
                    raise ValueError("saved-search absence cannot be verified with available API") from None
                searches = oci.pagination.list_call_get_all_results(
                    list_searches, compartment_id=compartment, limit=200
                ).data
                if any(search.id == entry["identity"] for search in searches):
                    raise ValueError("saved-search lookup returned 404 but inventory still contains it") from None
                entry["deleted"] = True
                continue
            delete = lambda e=entry, r=response: md.delete_management_saved_search(e["identity"], if_match=r.headers["etag"])
        elif kind == "source":
            getter = lambda name: la.get_source(journal.ns, name, compartment_id=compartment)
            try:
                response = owned_response(getter, journal, entry, compartment, tagged=False)
            except oci.exceptions.ServiceError as exc:
                if exc.status != 404:
                    raise
                from .provision_la import _find_source
                found = _find_source(la, journal.ns, compartment, entry["identity"], entry["identity"])
                if found:
                    raise
                entry["deleted"] = True
                continue
            delete = lambda e=entry, r=response: la.delete_source(journal.ns, e["identity"], if_match=r.headers["etag"])
        elif kind == "parser":
            getter = lambda name: la.get_parser(journal.ns, name)
            try:
                response = owned_response(getter, journal, entry, compartment, tagged=False)
            except oci.exceptions.ServiceError as exc:
                if exc.status != 404:
                    raise
                parsers = oci.pagination.list_call_get_all_results(la.list_parsers,
                    namespace_name=journal.ns, limit=200).data
                if any(p.name == entry["identity"] for p in parsers):
                    raise
                entry["deleted"] = True
                continue
            delete = lambda e=entry, r=response: la.delete_parser(journal.ns, e["identity"], if_match=r.headers["etag"])
        elif kind == "log_group":
            getter = lambda identity: la.get_log_analytics_log_group(journal.ns, identity)
            try:
                response = owned_response(getter, journal, entry, compartment)
            except oci.exceptions.ServiceError as exc:
                if exc.status != 404:
                    raise
                groups = oci.pagination.list_call_get_all_results(la.list_log_analytics_log_groups,
                    namespace_name=journal.ns, compartment_id=compartment, limit=200).data
                if any(g.id == entry["identity"] for g in groups):
                    raise
                entry["deleted"] = True
                continue
            delete = lambda e=entry, r=response: la.delete_log_analytics_log_group(journal.ns, e["identity"], if_match=r.headers["etag"])
        else:
            raise ValueError("unknown ownership journal resource kind")
        plan.append((entry, delete))
    order = {"dashboard": 0, "saved_search": 1, "source": 2, "parser": 3, "log_group": 4}
    if execute:
        for entry, delete in sorted(plan, key=lambda pair: order[pair[0]["kind"]]):
            delete()
            entry["deleted"] = True
            journal.save()
        # Preserved saved searches are an intentional fail-closed outcome, not
        # an incomplete destructive operation. The receipt reports the count.
        journal.data["cleanup_complete"] = True
        journal.save()
    return {"execute": execute, "cleanup_complete": True,
            "owned_content": len(plan), "preserved_shared_fields": preserved,
            "preserved_referenced_searches": preserved_searches}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="/etc/zpr-visibility/config.json")
    p.add_argument("--execute", action="store_true")
    args = p.parse_args(argv)
    cfg = read_config(args.config)
    session = build_session("instance_principal", None, None, cfg["region"])
    journal = Ownership(session, cfg["state_bucket"], cfg["installation_id"], cfg["compartment_id"])
    result = cleanup(journal, client(session, "log_analytics.LogAnalyticsClient"),
                     client(session, "management_dashboard.DashxApisClient"), cfg["compartment_id"], execute=args.execute)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
