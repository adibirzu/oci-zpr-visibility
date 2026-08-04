"""Command-line interface for OCI ZPR visibility."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .collector import ZprCollector
from .config import RunConfig
from .correlate import correlate_flow_records
from .findings import generate_findings
from .jsonutil import read_json, read_jsonl, write_json, write_jsonl
from .logging_ingestion import emit_records
from .logutil import emit
from .oci_clients import build_session
from .policy_parser import policy_statement_records
from .schema import FLOW_STATUS_NOT_CONFIGURED, new_run_id, normalize_records, run_record


def _session(args: argparse.Namespace) -> Any:
    cfg = RunConfig.from_args(args)  # validates auth/profile at startup
    return build_session(cfg.auth, cfg.config_file, cfg.profile, cfg.region)


def cmd_enable_zpr(args: argparse.Namespace) -> int:
    result = ZprCollector(_session(args)).enable_zpr(dry_run=args.dry_run)
    write_json(args.output, result)
    emit({"output": args.output, "dry_run": args.dry_run}, f"Wrote ZPR enablement response to {args.output}", args.json)
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    collector = ZprCollector(_session(args))
    snapshot = collector.collect(include_resources=not args.skip_resources, resource_query=args.resource_query)
    records = collector.records_for_snapshot(snapshot)
    findings = generate_findings(snapshot, [r for r in records if r.get("record_type") == "zpr_policy_statement"])
    run_id = new_run_id()
    snapshot_time = str(snapshot.get("snapshot_time") or "")
    all_records = normalize_records(
        [*records, *findings], run_id=run_id, inventory_snapshot_time=snapshot_time
    )
    all_records.append(
        run_record(
            run_id=run_id,
            event_time=snapshot_time,
            collection_status="SUCCEEDED_WITH_GAPS" if snapshot.get("collection_errors") else "SUCCEEDED",
            flow_collection_status=FLOW_STATUS_NOT_CONFIGURED,
            record_count=len(records),
            finding_count=len(findings),
            drift_count=0,
            flow_count=0,
            collection_error_count=int(
                snapshot.get("collection_error_count") or len(snapshot.get("collection_errors", []))
            ),
        )
    )

    write_json(args.snapshot, snapshot)
    write_jsonl(args.records, all_records)
    emitted = None
    if args.emit_log_id:
        emitted = emit_records(_session(args), args.emit_log_id, all_records, args.batch_size)
    payload = {"snapshot": args.snapshot, "records": args.records, "run_id": run_id,
               "record_count": len(all_records), "emitted": emitted}
    human = "\n".join(filter(None, [
        f"Emitted {emitted} records to OCI Logging log {args.emit_log_id}" if emitted is not None else None,
        f"Wrote snapshot to {args.snapshot}",
        f"Wrote {len(all_records)} normalized records to {args.records}",
    ]))
    emit(payload, human, args.json)
    return 0


def cmd_findings(args: argparse.Namespace) -> int:
    snapshot = read_json(args.snapshot)
    policy_records: list[dict[str, Any]] = []
    for policy in snapshot.get("zpr_policies", []):
        policy_records.extend(policy_statement_records(policy, snapshot.get("snapshot_time", "")))
    findings = normalize_records(
        generate_findings(snapshot, policy_records),
        run_id=new_run_id(),
        inventory_snapshot_time=str(snapshot.get("snapshot_time") or ""),
    )
    write_jsonl(args.output, findings)
    emit({"output": args.output, "finding_count": len(findings)},
         f"Wrote {len(findings)} findings to {args.output}", args.json)
    return 0


def cmd_correlate(args: argparse.Namespace) -> int:
    snapshot = read_json(args.snapshot)
    policy_records: list[dict[str, Any]] = []
    for policy in snapshot.get("zpr_policies", []):
        policy_records.extend(policy_statement_records(policy, snapshot.get("snapshot_time", "")))
    if args.flow_log_group_id:
        from datetime import datetime, timedelta, timezone

        from .flow_logs import fetch_flow_logs
        session = _session(args)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=args.lookback_days)
        fmt = "%Y-%m-%dT%H:%M:%S.000Z"
        flows = fetch_flow_logs(
            session, args.compartment_id or session.tenancy_id,
            args.flow_log_group_id, args.flow_log_id,
            start.strftime(fmt), end.strftime(fmt),
        )
    elif args.flows:
        flows = read_jsonl(args.flows)
    else:
        print("provide --flows <jsonl> or --flow-log-group-id <ocid>", file=sys.stderr)
        return 2
    enriched = normalize_records(
        correlate_flow_records(flows, snapshot, policy_records),
        run_id=new_run_id(),
        inventory_snapshot_time=str(snapshot.get("snapshot_time") or ""),
    )
    write_jsonl(args.output, enriched)
    emit({"output": args.output, "enriched_count": len(enriched), "flow_count": len(flows)},
         f"Wrote {len(enriched)} enriched flow records to {args.output}", args.json)
    return 0


def cmd_emit(args: argparse.Namespace) -> int:
    records = read_jsonl(args.records)
    emitted = emit_records(_session(args), args.log_id, records, args.batch_size)
    emit({"log_id": args.log_id, "emitted": emitted},
         f"Emitted {emitted} records to OCI Logging log {args.log_id}", args.json)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    root = Path(args.output_dir)
    snapshot = read_json(Path("examples/sample_snapshot.json"))
    flows = read_jsonl(Path("examples/sample_flow_logs.jsonl"))
    policy_records: list[dict[str, Any]] = []
    for policy in snapshot.get("zpr_policies", []):
        policy_records.extend(policy_statement_records(policy, snapshot.get("snapshot_time", "")))
    run_id = new_run_id()
    snapshot_time = str(snapshot.get("snapshot_time") or "")
    statements = normalize_records(
        policy_records, run_id=run_id, inventory_snapshot_time=snapshot_time
    )
    findings = normalize_records(
        generate_findings(snapshot, policy_records),
        run_id=run_id,
        inventory_snapshot_time=snapshot_time,
    )
    enriched = normalize_records(
        correlate_flow_records(flows, snapshot, policy_records),
        run_id=run_id,
        inventory_snapshot_time=snapshot_time,
    )
    write_json(root / "snapshot.json", snapshot)
    write_jsonl(root / "records.jsonl", [*statements, *findings])
    write_jsonl(root / "enriched_flows.jsonl", enriched)
    emit({"output_dir": str(root), "policy_records": len(policy_records),
          "findings": len(findings), "enriched": len(enriched)},
         f"Wrote demo outputs under {root}", args.json)
    return 0


def add_auth_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--auth", choices=["api_key", "instance_principal", "resource_principal"], default="api_key")
    parser.add_argument("--config-file", default=None)
    parser.add_argument("--profile", default="DEFAULT")
    parser.add_argument("--region", default=None)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON result")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oci-zpr-visibility")
    parser.add_argument("--version", action="version", version=f"oci-zpr-visibility {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    enable = sub.add_parser("enable-zpr", help="Enable ZPR in the tenancy root compartment.")
    add_auth_args(enable)
    enable.add_argument("--dry-run", action="store_true")
    enable.add_argument("--output", default="out/zpr_enable_response.json")
    enable.set_defaults(func=cmd_enable_zpr)

    collect = sub.add_parser("collect", help="Collect ZPR inventory and write normalized records.")
    add_auth_args(collect)
    collect.add_argument("--snapshot", default="out/zpr_snapshot.json")
    collect.add_argument("--records", default="out/zpr_records.jsonl")
    collect.add_argument("--resource-query", default=None)
    collect.add_argument("--skip-resources", action="store_true")
    collect.add_argument("--emit-log-id", default=None)
    collect.add_argument("--batch-size", type=int, default=100)
    collect.set_defaults(func=cmd_collect)

    findings = sub.add_parser("findings", help="Generate findings from an existing snapshot.")
    findings.add_argument("--snapshot", required=True)
    findings.add_argument("--output", default="out/zpr_findings.jsonl")
    findings.add_argument("--json", action="store_true", help="emit machine-readable JSON result")
    findings.set_defaults(func=cmd_findings)

    correlate = sub.add_parser("correlate", help="Correlate VCN flow logs (JSONL or live OCI Logging) with a ZPR snapshot.")
    add_auth_args(correlate)  # auth flags + --json (needed when fetching live flow logs)
    correlate.add_argument("--snapshot", required=True)
    correlate.add_argument("--flows", default=None, help="local JSONL flow records (omit when fetching live)")
    correlate.add_argument("--flow-log-group-id", default=None, help="fetch real VCN flow logs from this OCI Logging log group")
    correlate.add_argument("--flow-log-id", default=None, help="VCN flow log OCID (with --flow-log-group-id)")
    correlate.add_argument("--compartment-id", default=None)
    correlate.add_argument("--lookback-days", type=int, default=1)
    correlate.add_argument("--output", default="out/zpr_enriched_flows.jsonl")
    correlate.set_defaults(func=cmd_correlate)

    emit = sub.add_parser("emit", help="Emit normalized JSONL records to an OCI custom log.")
    add_auth_args(emit)
    emit.add_argument("--records", required=True)
    emit.add_argument("--log-id", required=True)
    emit.add_argument("--batch-size", type=int, default=100)
    emit.set_defaults(func=cmd_emit)

    demo = sub.add_parser("demo", help="Run local sample data through findings and correlation.")
    demo.add_argument("--output-dir", default="out/demo")
    demo.add_argument("--json", action="store_true", help="emit machine-readable JSON result")
    demo.set_defaults(func=cmd_demo)

    # Consolidated operational subcommands are listed here for `--help`, but are
    # routed in main() before argparse so their flags pass through verbatim to the
    # delegated module's own argparse (the single source of truth). See _delegate.
    for name, _module_name, helptext in _DELEGATED_SUBCOMMANDS:
        sub.add_parser(name, help=helptext, add_help=False)

    return parser


# (subcommand, package module under oci_zpr_visibility, help text)
_DELEGATED_SUBCOMMANDS = [
    ("discover", "discover", "Discover an existing tenancy's ZPR setup + print continuous-collection steps."),
    ("provision-la", "provision_la", "Provision LA fields/parser/source/log group; --upload to ingest records."),
    ("validate-dashboards", "validate_dashboards", "Execute dashboard queries against live LA (per-widget data/zero/error status)."),
    ("seed", "seed", "Create the 'app' security attribute and a real ZPR policy."),
    ("trigger", "trigger", "Generate flows exercising every detection classification."),
    ("deploy-dashboard", "deploy_dashboard", "Build + import the OCI LA dashboard (--dry-run to preview)."),
    ("refresh", "refresh", "Scheduled unit: collect -> drift -> upload to Log Analytics."),
]
_DELEGATED_MODULES = {name: module for name, module, _help in _DELEGATED_SUBCOMMANDS}


def _delegate(subcommand: str, argv: list[str]) -> int:
    """Forward remaining args to the delegated package module's main()."""
    import importlib

    module = importlib.import_module(f"oci_zpr_visibility.{_DELEGATED_MODULES[subcommand]}")
    return int(module.main(argv))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # Route consolidated subcommands before argparse so their flags pass through.
    if argv and argv[0] in _DELEGATED_MODULES:
        return _delegate(argv[0], argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
