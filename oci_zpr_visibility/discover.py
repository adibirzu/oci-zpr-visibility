"""Discover an existing tenancy's ZPR setup and print the steps to stand up
continuous visibility collection against it.

This is the entry point for users who already run ZPR (not the bundled demo).
It performs a **read-only** pass — ZPR config, policies, the `oracle-zpr`
security attributes, protected resources — and locates VCN Flow Logs in the
target compartment, then emits the exact `provision-la` / `refresh` commands
(with the discovered flow-log OCIDs) needed for the same 15-minute collection
loop the demo uses.

Usage:
  oci-zpr-visibility discover --auth api_key --profile <p> --region <r>
  oci-zpr-visibility discover --auth instance_principal --json
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from .collector import ZprCollector
from .oci_clients import build_session, client, OciSession


def _list_all(session: OciSession, func: Any, *args: Any, **kwargs: Any) -> list[Any]:
    return list(session.oci.pagination.list_call_get_all_results(func, *args, **kwargs).data)


def _compartment_ids(session: OciSession, explicit: str | None) -> list[str]:
    """If a compartment is given, search just it; otherwise tenancy root + ACTIVE subtree."""
    if explicit:
        return [explicit]
    ids = [session.tenancy_id]
    try:
        identity = client(session, "identity.IdentityClient")
        ids += [
            c.id
            for c in _list_all(
                session, identity.list_compartments, session.tenancy_id,
                compartment_id_in_subtree=True, access_level="ANY", lifecycle_state="ACTIVE",
            )
        ]
    except Exception:
        pass
    return ids


def _discover_flow_logs(session: OciSession, compartment_ids: list[str]) -> list[dict[str, str]]:
    """Best-effort: find VCN Flow Logs (service log, source.service == 'flowlogs')."""
    found: list[dict[str, str]] = []
    try:
        log_mgmt = client(session, "logging.LoggingManagementClient")
    except Exception:
        return found
    for compartment_id in compartment_ids:
        try:
            groups = _list_all(session, log_mgmt.list_log_groups, compartment_id=compartment_id)
        except Exception:
            continue
        for group in groups:
            try:
                logs = _list_all(session, log_mgmt.list_logs, group.id)
            except Exception:
                continue
            for log in logs:
                source = getattr(getattr(log, "configuration", None), "source", None)
                service = getattr(source, "service", "") or ""
                if service.lower() == "flowlogs":
                    found.append(
                        {
                            "flow_log_compartment_id": compartment_id,
                            "flow_log_group_id": group.id,
                            "flow_log_id": log.id,
                            "flow_log_name": getattr(log, "display_name", "") or "",
                        }
                    )
    return found


def discover(session: OciSession, compartment_id: str | None = None) -> dict[str, Any]:
    collector = ZprCollector(session)
    snapshot = collector.collect(include_resources=True)

    config = snapshot.get("zpr_configuration") or {}
    config_enabled = isinstance(config, dict) and "error" not in config
    zpr_status = config.get("zpr_status") or config.get("lifecycle_state") if config_enabled else None

    policies = snapshot.get("zpr_policies", [])
    policy_summaries = [
        {
            "name": p.get("name"),
            "lifecycle_state": p.get("lifecycle_state"),
            "statements": len(p.get("statements", []) or []),
        }
        for p in policies
    ]

    attributes = snapshot.get("security_attributes", [])
    oracle_zpr_attrs = [a.get("name") for a in attributes if (a.get("namespace_name") == "oracle-zpr")]

    resources = snapshot.get("resources", [])
    protected = [r for r in resources if r.get("normalized_security_attributes")]
    protected_by_type: dict[str, int] = {}
    for r in protected:
        rt = str(r.get("resource_type") or "unknown")
        protected_by_type[rt] = protected_by_type.get(rt, 0) + 1

    flow_logs = _discover_flow_logs(session, _compartment_ids(session, compartment_id))

    return {
        "tenancy_id": session.tenancy_id,
        "region": session.region,
        "zpr_enabled": config_enabled,
        "zpr_status": zpr_status,
        "policy_count": len(policies),
        "policies": policy_summaries,
        "oracle_zpr_attributes": oracle_zpr_attrs,
        "protected_resource_count": len(protected),
        "protected_by_type": protected_by_type,
        "flow_logs": flow_logs,
    }


def _print_report(report: dict[str, Any]) -> None:
    print("=== OCI ZPR discovery ===")
    print(f"tenancy : {report['tenancy_id']}")
    print(f"region  : {report['region']}")
    status = report.get("zpr_status") or ("ACTIVE" if report["zpr_enabled"] else "NOT ENABLED")
    print(f"ZPR     : {'enabled' if report['zpr_enabled'] else 'NOT enabled'} ({status})")
    print()
    print(f"Policies ({report['policy_count']}):")
    for p in report["policies"]:
        print(f"  - {p['name']}  [{p['lifecycle_state']}]  {p['statements']} statement(s)")
    if not report["policies"]:
        print("  (none — create a ZPR policy before collection has anything to show)")
    print()
    print(f"oracle-zpr attributes: {', '.join(report['oracle_zpr_attributes']) or '(none)'}")
    print(f"Protected resources  : {report['protected_resource_count']} "
          f"({', '.join(f'{k}={v}' for k, v in report['protected_by_type'].items()) or 'none'})")
    print()
    print(f"VCN Flow Logs found ({len(report['flow_logs'])}):")
    for fl in report["flow_logs"]:
        print(f"  - {fl['flow_log_name'] or '(unnamed)'}")
        print(f"      group: {fl['flow_log_group_id']}")
        print(f"      log  : {fl['flow_log_id']}")
    if not report["flow_logs"]:
        print("  (none in this compartment — enable VCN Subnet Flow Logs, or pass --compartment-id)")
    print()
    _print_next_steps(report)


def _print_next_steps(report: dict[str, Any]) -> None:
    print("=== Next steps: stand up continuous collection ===")
    if not report["zpr_enabled"]:
        print("0. Enable ZPR for the tenancy first (one-time): `oci-zpr-visibility enable-zpr`")
        print("   or the Console / Terraform `oci_zpr_configuration`.")
    print("1. Provision the Log Analytics source/parser/fields (idempotent):")
    print("     oci-zpr-visibility provision-la --auth <auth> --profile <p> --region <r>")
    print("2. Run one refresh (collect -> correlate -> upload -> metrics):")
    flow = report["flow_logs"][0] if report["flow_logs"] else None
    refresh = ("     oci-zpr-visibility refresh --auth <auth> --profile <p> --region <r> \\\n"
               "       --state-bucket <object-storage-bucket>")
    if flow:
        refresh += (" \\\n"
                    f"       --flow-log-compartment-id {flow['flow_log_compartment_id']} \\\n"
                    f"       --flow-log-group-id {flow['flow_log_group_id']} \\\n"
                    f"       --flow-log-id {flow['flow_log_id']}")
    else:
        refresh += " \\\n       --flow-log-group-id <group-ocid> --flow-log-id <log-ocid>"
    print(refresh)
    print("3. Import the dashboard:")
    print("     oci-zpr-visibility deploy-dashboard --auth <auth> --profile <p> --region <r>")
    print("4. Schedule it. Pick one:")
    print("   - Controller VM: add a 15-minute cron running the `refresh` command above")
    print("     (use --auth instance_principal on the VM; no API keys).")
    print("   - OCI Function: deploy functions/func.py (--auth resource_principal) and drive")
    print("     it from Connector Hub / API Gateway / a scheduler.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="oci-zpr-visibility discover")
    parser.add_argument("--auth", choices=["api_key", "instance_principal", "resource_principal"], default="api_key")
    parser.add_argument("--config-file")
    parser.add_argument("--profile")
    parser.add_argument("--region")
    parser.add_argument("--compartment-id", help="Compartment to search for VCN Flow Logs (defaults to tenancy root).")
    parser.add_argument("--json", action="store_true", help="Emit the discovery report as JSON.")
    args = parser.parse_args(argv)

    session = build_session(args.auth, args.config_file, args.profile, args.region)
    report = discover(session, compartment_id=args.compartment_id)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
